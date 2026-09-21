"""Analytics agent — for operating businesses only. Takes the founder's REAL
reported numbers for a period (and, if uploaded, their order history), computes
the ratios in code, and writes the summary the Strategy agent plans from.

It never sees simulated data and never fills in a number the founder didn't
give: a ratio whose inputs are missing comes back as None and is shown as
"not reported". A business that hasn't launched skips this agent entirely --
there is nothing to measure yet.

A Google ADK LlmAgent writes the narrative; the arithmetic (compute_kpis, and
tools/orders_file.order_metrics for uploads) is plain Python and unit-tested
-- the same principle as Finance's guardrail.
"""

import asyncio
import time
from dataclasses import asdict, dataclass

from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from agents._cache import cached
from agents._models import AGENT_MAX_TOKENS, GROQ_MODEL_ADK_JSON
from agents._money import fmt_money
from agents._retry import retry_on_rate_limit
from agents._text import as_list
from observability.usage import record_adk_usage

APP_NAME = "flywheel"
USER_ID = "flywheel_run"
# Analytics is on ADK's output_schema, which parses whatever text comes back --
# so it needs a model that emits bare JSON with no preamble, same as Strategy.
DEFAULT_MODEL = GROQ_MODEL_ADK_JSON

_INSTRUCTION = """You are the Analytics agent for Flywheel, an AI co-founder. You're given an
operating business's REAL numbers for a period, as entered by the founder, the ratios
computed from them, any earlier periods, and -- if they uploaded one -- figures computed
from their order history.

Return JSON with two fields and nothing else -- no preamble, no code fence:
- headline: ONE sentence, the single most important thing these numbers say. This is
  what the founder reads first, so it must carry the finding, not introduce it. Write
  "Revenue grew 18% but net margin fell to 4%", never "Here is a summary of the numbers".
- points: 2-4 further findings as a JSON array of strings, one finding per entry, each a
  complete sentence. Cover how the numbers compare with earlier periods or recent months,
  and what the plan should change. Never put two findings in one entry.

Use only the numbers you're given. Anything marked "not reported" is unknown -- say so if
it matters, but never estimate it. If the form's revenue and the order file's revenue
differ a lot, say so: they may cover different periods. Keep amounts in the stated
currency."""


class AnalyticsSchema(BaseModel):
    headline: str = Field(description="One sentence: the single most important finding in these numbers")
    points: list[str] = Field(
        default_factory=list, description="2-4 further findings, one per entry, each a complete sentence"
    )


@dataclass
class PeriodMetrics:
    """What the founder reports for one period. The first four are required;
    the rest are optional because many small businesses don't track them."""

    period_label: str
    revenue: float
    net_profit: float
    total_debt: float
    period_months: int = 12
    ebitda: float | None = None
    cash_in_bank: float | None = None
    marketing_spend: float | None = None
    new_customers: int | None = None
    customers_at_start: int | None = None
    customers_lost: int | None = None


def _ratio(numerator, denominator):
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator, 4)


def compute_kpis(m: PeriodMetrics) -> dict:
    """Ratios from reported numbers only. A missing input gives None, never a guess."""
    customers_at_end = None
    if None not in (m.customers_at_start, m.new_customers, m.customers_lost):
        customers_at_end = m.customers_at_start + m.new_customers - m.customers_lost
    annual_revenue = m.revenue * 12 / max(int(m.period_months), 1)
    return {
        "net_margin": _ratio(m.net_profit, m.revenue),
        "ebitda_margin": _ratio(m.ebitda, m.revenue),
        # Against a year of revenue, so a one-month period isn't read as 12x the debt load.
        "debt_to_revenue": _ratio(m.total_debt, annual_revenue),
        "cac": _ratio(m.marketing_spend, m.new_customers),
        "churn_rate": _ratio(m.customers_lost, m.customers_at_start),
        "customers_at_end": customers_at_end,
        "revenue_per_customer": _ratio(m.revenue, customers_at_end),
    }


_MONEY_FIELDS = (
    ("revenue", "Revenue"),
    ("net_profit", "Net profit"),
    ("ebitda", "EBITDA"),
    ("total_debt", "Total debt"),
    ("cash_in_bank", "Cash in bank"),
    ("marketing_spend", "Marketing spend"),
)
_COUNT_FIELDS = (
    ("customers_at_start", "Customers at start"),
    ("new_customers", "New customers"),
    ("customers_lost", "Customers lost"),
    ("customers_at_end", "Customers at end"),
)
_PERCENT_FIELDS = (
    ("net_margin", "Net margin"),
    ("ebitda_margin", "EBITDA margin"),
    ("debt_to_revenue", "Debt/annual revenue"),
    ("churn_rate", "Churn"),
)


def describe_period(metrics: dict, kpis: dict, currency: str) -> str:
    """One period's numbers as text for a prompt. Takes plain dicts so it
    works equally on a fresh PeriodMetrics and on records read back from the
    database."""
    values = {**metrics, **kpis}
    parts = [f"Period length: {values.get('period_months', 12)} months"]
    for key, label in _MONEY_FIELDS:
        v = values.get(key)
        parts.append(f"{label}: {fmt_money(v, currency) if v is not None else 'not reported'}")
    for key, label in _COUNT_FIELDS:
        v = values.get(key)
        parts.append(f"{label}: {v:,}" if v is not None else f"{label}: not reported")
    for key, label in (("cac", "CAC"), ("revenue_per_customer", "Revenue per customer")):
        v = values.get(key)
        parts.append(f"{label}: {fmt_money(v, currency) if v is not None else 'not reported'}")
    for key, label in _PERCENT_FIELDS:
        v = values.get(key)
        parts.append(f"{label}: {v:.1%}" if v is not None else f"{label}: not reported")
    return f"{metrics.get('period_label', 'Period')} -- " + "; ".join(parts)


def describe_file_metrics(fm: dict, currency: str) -> str:
    """Figures computed from an uploaded order history, as prompt text."""
    change = fm.get("revenue_change_last_3m_vs_prior_3m")
    recent = list(fm.get("monthly_revenue", {}).items())[-6:]
    trend = f"{change:+.0%}" if change is not None else "not enough history"
    return (
        f"Uploaded orders {fm['first_order']} to {fm['last_order']}: {fm['orders']:,} orders from "
        f"{fm['customers']:,} customers, revenue {fmt_money(fm['revenue'], currency)}, average order "
        f"{fmt_money(fm['average_order_value'], currency)}, repeat-customer rate "
        f"{fm['repeat_customer_rate']:.0%}, last 3 months vs previous 3: {trend}. Monthly revenue, "
        "latest months: " + ", ".join(f"{m} {fmt_money(v, currency)}" for m, v in recent) + "."
    )


@dataclass
class AnalyticsReport:
    cycle: int
    currency: str
    period_label: str
    metrics: dict
    kpis: dict
    # headline + points are what the UI renders. `summary` is the same content
    # as one string, and is what Strategy is given as prompt context and what
    # the CLIs print -- keeping it means no downstream consumer has to join the
    # points back together, and Decision Records written before this change
    # still read back.
    headline: str
    points: list
    summary: str
    file_metrics: dict | None = None


class AnalyticsAgent:
    """Google ADK LlmAgent for the narrative summary; the ratios are plain
    Python (compute_kpis) and deterministic on purpose."""

    def __init__(self, model: str = DEFAULT_MODEL, session_id: str = "analytics_session"):
        self.model_name = model
        resolved_model = (
            LiteLlm(model=model, max_tokens=AGENT_MAX_TOKENS["analytics"]) if model.startswith("groq/") else model
        )
        self._agent = LlmAgent(
            name="analytics_agent",
            model=resolved_model,
            instruction=_INSTRUCTION,
            output_schema=AnalyticsSchema,
            output_key="analytics_output",
        )
        self._session_service = InMemorySessionService()
        self._runner = Runner(agent=self._agent, app_name=APP_NAME, session_service=self._session_service)
        self._session_id = session_id
        self._session_ready = False

    async def _ensure_session(self):
        if not self._session_ready:
            await self._session_service.create_session(
                app_name=APP_NAME, user_id=USER_ID, session_id=self._session_id
            )
            self._session_ready = True

    async def _summarize_async(
        self,
        cycle: int,
        metrics: PeriodMetrics,
        currency: str,
        business_summary: str,
        history: list[dict],
        file_metrics: dict | None,
    ) -> AnalyticsReport:
        await self._ensure_session()

        kpis = compute_kpis(metrics)
        # Earlier periods are passed in explicitly rather than left to ADK
        # session memory: each dashboard run builds a fresh agent, so the
        # session wouldn't remember them.
        lines = [
            f"Business: {business_summary}",
            f"Currency: {currency}",
            f"This period: {describe_period(asdict(metrics), kpis, currency)}",
        ]
        if file_metrics:
            lines.append(describe_file_metrics(file_metrics, currency))
        if history:
            lines.append("Earlier periods, oldest first:")
            lines += [f"- {describe_period(h['metrics'], h['kpis'], currency)}" for h in history]
        else:
            lines.append("No earlier periods reported.")

        content = types.Content(role="user", parts=[types.Part(text="\n".join(lines))])

        summary = None
        usage = []
        started = time.perf_counter()
        async for event in self._runner.run_async(user_id=USER_ID, session_id=self._session_id, new_message=content):
            if getattr(event, "usage_metadata", None):
                usage.append(event.usage_metadata)
            if event.is_final_response() and event.content and event.content.parts:
                summary = event.content.parts[0].text
        record_adk_usage("analytics", self.model_name, usage, started)

        if summary is None:
            raise RuntimeError("Analytics agent produced no response")

        parsed = AnalyticsSchema.model_validate_json(summary)
        headline = parsed.headline.strip()
        points = as_list(parsed.points)
        return AnalyticsReport(
            cycle=cycle,
            currency=currency,
            period_label=metrics.period_label,
            metrics=asdict(metrics),
            kpis=kpis,
            headline=headline,
            points=points,
            summary=" ".join([headline, *points]).strip(),
            file_metrics=file_metrics,
        )

    @cached("analytics", AnalyticsReport)
    @retry_on_rate_limit()
    def summarize(
        self,
        cycle: int,
        metrics: PeriodMetrics,
        currency: str,
        business_summary: str,
        history: list[dict] | None = None,
        file_metrics: dict | None = None,
    ) -> AnalyticsReport:
        return asyncio.run(
            self._summarize_async(cycle, metrics, currency, business_summary, history or [], file_metrics)
        )
