"""The planning engine: Strategy -> Finance -> [Marketing, Product, Sales, (CRM)].

Two entry points, one for each kind of business:

  run_launch_plan()      Not launched yet. One pass from the market research
                         and the Founder Advisor's verdict to a specific
                         launch plan. No Analytics (nothing to measure yet)
                         and no CRM (no customers yet).
  run_business_review()  Operating business. Analytics reads the founder's
                         real numbers and uploaded order history first;
                         Strategy plans from them; CRM works on the customers
                         in the upload.

run_funding() then turns either plan into a funding roadmap.

Token discipline: the context is kept as named sections. Strategy and Funding
see all of it; each planning agent gets only the sections it uses
(AGENT_CONTEXT), instead of every agent receiving the whole research, all the
founder's answers and every number.

What is deliberately NOT here:
  - The market simulator. simulator/market_simulator.py and its tests still
    exist but aren't wired in: made-up revenue for a business that hasn't
    launched was misleading.
  - A hardcoded budget. Every amount is the founder's own figure.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, fields, replace

import pandas as pd

from agents._brief import EXISTING, LAUNCH, OFFERING_LABELS, PlanBrief
from agents._guardrails import clean_text_fields, funding_problems, strategy_problems
from agents._money import fmt_money
from agents._segments import customer_table, describe_segments, segment_summary
from agents._text import as_text
from agents.analytics import AnalyticsAgent, AnalyticsReport, PeriodMetrics, describe_file_metrics, describe_period
from agents.crm import CRMAgent, CRMOutput
from agents.finance import BudgetAllocation, FinanceAgent
from agents.founder_advisor import AdvisorDecision
from agents.funding import FundingAgent, FundingPlan
from agents.intake import BusinessInput
from agents.market_research import MarketResearchReport
from agents.marketing import MarketingOutput
from agents.product import ProductAgent, ProductOutput
from agents.sales import SalesAgent, SalesOutput
from agents.strategy import StrategyAgent, StrategyDecision
from observability.decision_record import DecisionRecord, get_records, log_decision
from orchestration.a2a_bridge import request_marketing
from tools.mcp_client_tool import query_decision_records
from tools.orders_file import order_metrics

# Validation agents (intake, research, advisor, formation) log under period 0:
# they run before any plan exists.
PRECYCLE = 0
# A launch plan is a single pass, so it's always period 1.
LAUNCH_CYCLE = 1
AREAS = ("marketing", "product", "sales", "crm")

# Which context sections each planning agent actually uses.
AGENT_CONTEXT = {
    "marketing": ("research", "advisor", "analytics", "orders", "segments"),
    "sales": ("research", "founder_answers", "advisor", "analytics", "orders"),
    "product": ("capital_costs", "founder_answers", "numbers", "orders"),
    # CRM gets its customer groups directly; the analytics summary is the only extra it needs.
    "crm": ("analytics",),
}


class PlanBlocked(ValueError):
    """The plan can't go ahead, e.g. the cash reserve uses all the capital.
    The message says why, in the founder's terms."""


@dataclass
class PlanResult:
    brief: PlanBrief
    strategy: StrategyDecision
    allocation: BudgetAllocation
    marketing: MarketingOutput
    marketing_transport: str
    product: ProductOutput
    sales: SalesOutput
    crm: CRMOutput | None = None
    analytics: AnalyticsReport | None = None


def planning_areas(mode: str, has_orders: bool) -> tuple[str, ...]:
    """CRM only plans when there are real customers to work with: an operating
    business that uploaded its order history."""
    return AREAS if mode == EXISTING and has_orders else AREAS[:3]


def _clean_output(output):
    """A planning agent's output with any leaked tool-call markup cut off.
    Applied here rather than inside each agent, so cached answers stay valid."""
    return replace(output, **{f.name: clean_text_fields(getattr(output, f.name)) for f in fields(output)})


def join_context(sections: dict, keys=None) -> str:
    """The named context sections as prompt text; all of them if keys is None."""
    return "\n".join(sections[k] for k in (keys if keys is not None else sections) if sections.get(k))


def previous_segments(cycle: int) -> dict | None:
    """Last period's CRM customer segments, fetched over MCP from the Decision
    Record server running as a separate process."""
    earlier = [r for r in query_decision_records(agent="crm") if r["cycle"] < cycle]
    if not earlier:
        return None
    return max(earlier, key=lambda r: r["cycle"])["decision"].get("segments")


def _checked_strategy(
    cycle: int, mode: str, business: BusinessInput, context: str, reference_price: float | None
) -> StrategyDecision:
    """Strategy's plan, checked by agents/_guardrails.py before anyone uses it.

    A plan that fails the checks goes back once, in the same ADK session, with
    the problems listed. A second failure blocks the plan: passing a plan about
    the wrong business, or with demeaning wording, to every other agent is
    worse than stopping.
    """
    offering = OFFERING_LABELS.get(business.offering_type, business.offering_type)
    business_line = (
        f"The business: {business.business_summary} It sells {business.product_or_service} ({offering}) "
        f"in {business.target_region}. All prices in {business.currency}."
    )
    agent = StrategyAgent()
    feedback = ""
    problems: list[str] = []
    for attempt in (1, 2):
        decision = agent.decide(cycle, mode, business.currency, context + feedback, business_line)
        problems = strategy_problems(decision, business, reference_price)
        if not problems:
            log_decision(
                DecisionRecord(cycle, "strategy", {"mode": mode, "context": context, "attempt": attempt}, asdict(decision))
            )
            return decision
        log_decision(DecisionRecord(cycle, "strategy_rejected", {"attempt": attempt, "problems": problems}, asdict(decision)))
        feedback = "\n\nYour previous plan was rejected by the plan checker: " + " ".join(problems) + " Fix every one of these."
    raise PlanBlocked("Strategy produced an unusable plan twice. " + " ".join(problems))


def _plan(
    cycle: int,
    mode: str,
    business: BusinessInput,
    sections: dict,
    metrics: PeriodMetrics | None = None,
    budget: float | None = None,
    segments: dict | None = None,
    reference_price: float | None = None,
) -> PlanResult:
    currency = business.currency
    areas = planning_areas(mode, segments is not None)
    context = f"{join_context(sections)}\nBudget areas this period: {', '.join(areas)}."

    strategy = _checked_strategy(cycle, mode, business, context, reference_price)

    # An area this plan doesn't include gets no share, whatever Strategy asked for.
    priorities = {k: (v if k in areas else 0.0) for k, v in strategy.priorities.items()}
    finance = FinanceAgent(currency=currency)
    if mode == LAUNCH:
        allocation = finance.plan_launch(
            cycle,
            priorities,
            capital=business.starting_capital,
            price=strategy.price,
            monthly_fixed_costs=business.monthly_fixed_costs,
            unit_cost=business.unit_cost,
            runway_months=business.runway_months,
        )
    else:
        allocation = finance.plan_operating(cycle, priorities, metrics, budget)
    log_decision(DecisionRecord(cycle, "finance", {"priorities": priorities}, asdict(allocation)))

    if allocation.total_budget <= 0:
        reasons = " ".join(allocation.health.get("warnings", [])) or "The budget is zero."
        raise PlanBlocked(f"Nothing left to plan with. {reasons}")

    base_brief = PlanBrief(
        cycle=cycle,
        mode=mode,
        business_summary=business.business_summary,
        industry=business.industry,
        product_or_service=business.product_or_service,
        region=business.target_region,
        currency=currency,
        positioning=strategy.positioning,
        target_customer=strategy.target_customer,
        price=strategy.price,
        price_unit=strategy.price_unit,
        offering_type=business.offering_type,
    )
    briefs = {name: replace(base_brief, context=join_context(sections, AGENT_CONTEXT[name])) for name in areas}

    # The planning agents are independent: each needs only its brief and its
    # own slice of the budget, and none reads another's output. Running them
    # concurrently makes this stage as slow as the slowest agent rather than
    # the sum of all of them.
    #
    # Marketing goes through request_marketing(), which routes over A2A when
    # the bridge server is running (see orchestration/a2a_bridge.py) and
    # falls back to an in-process call otherwise.
    with ThreadPoolExecutor(max_workers=len(areas)) as pool:
        futures = {
            "marketing": pool.submit(request_marketing, briefs["marketing"], allocation.marketing),
            "product": pool.submit(ProductAgent().execute, briefs["product"], allocation.product),
            "sales": pool.submit(SalesAgent().execute, briefs["sales"], allocation.sales),
        }
        if "crm" in areas:
            futures["crm"] = pool.submit(
                CRMAgent().execute, briefs["crm"], allocation.crm, segments, previous_segments(cycle)
            )
        # .result() re-raises in the caller, so a failing agent still surfaces
        # rather than being silently swallowed by the pool.
        marketing, transport = futures["marketing"].result()
        outputs = {name: f.result() for name, f in futures.items() if name != "marketing"}

    # Models occasionally leak raw tool-call markup into a text field (seen in a
    # live Sales run); cut it off before anything is logged or shown.
    marketing = _clean_output(marketing)
    outputs = {name: _clean_output(out) for name, out in outputs.items()}

    logged = {"marketing": marketing, **outputs}
    for name, out in logged.items():
        snapshot = {"budget": getattr(allocation, name), "brief": asdict(briefs[name])}
        # Record which transport Marketing used, so the Decision Record shows
        # whether A2A was actually exercised rather than leaving it ambiguous
        # after a silent fallback.
        if name == "marketing":
            snapshot["transport"] = transport
        log_decision(DecisionRecord(cycle, name, snapshot, asdict(out)))

    return PlanResult(
        base_brief, strategy, allocation, marketing, transport, outputs["product"], outputs["sales"], outputs.get("crm")
    )


# ------------------------------------------------------------- new idea --


def launch_sections(
    business: BusinessInput,
    research: MarketResearchReport,
    decision: AdvisorDecision,
    qa_answers: dict[str, str] | None = None,
) -> dict:
    currency = business.currency
    answers = "\n".join(f"- Q: {q} A: {a}" for q, a in (qa_answers or {}).items())
    return {
        "capital_costs": (
            f"Founder's capital for the launch: {fmt_money(business.starting_capital, currency)}. "
            f"Monthly fixed costs: {fmt_money(business.monthly_fixed_costs, currency)}; cost to deliver one unit: "
            f"{fmt_money(business.unit_cost, currency)} ('—' means not given)."
        ),
        # as_text, not the raw field: these are lists of points now, and an
        # f-string would hand the model a Python repr full of brackets and quotes.
        "research": (
            f"Market research: size {research.market_size_estimate} "
            f"Competitors: {as_text(research.key_competitors)} "
            f"Opportunities: {as_text(research.opportunities)} Risks: {as_text(research.risks)}"
        ),
        "founder_answers": f"Founder's answers:\n{answers}" if answers else "",
        "advisor": (
            f"Founder Advisor verdict: {decision.verdict} -- {as_text(decision.rationale)} Seed plan: positioning "
            f"'{decision.seed_positioning}', price {fmt_money(decision.seed_price, currency)} "
            f"{decision.seed_price_unit}, budget priorities {decision.seed_priorities}."
        ),
    }


def run_launch_plan(
    business: BusinessInput,
    research: MarketResearchReport,
    decision: AdvisorDecision,
    qa_answers: dict[str, str] | None = None,
) -> PlanResult:
    """New idea -> one specific launch plan, funded from the founder's capital."""
    return _plan(
        LAUNCH_CYCLE,
        LAUNCH,
        business,
        launch_sections(business, research, decision, qa_answers),
        reference_price=decision.seed_price or None,
    )


# ----------------------------------------------------- operating business --


def analytics_history() -> list[dict]:
    """Every reported period's Analytics record, oldest first -- the founder's
    real numbers read back from the Decision Records."""
    history = [json.loads(r["decision"]) for r in get_records(agent="analytics")]
    return sorted(history, key=lambda h: h["cycle"])


def next_review_cycle() -> int:
    periods = [r["cycle"] for r in get_records() if r["cycle"] > PRECYCLE]
    return max(periods, default=0) + 1


def run_business_review(
    business: BusinessInput,
    metrics: PeriodMetrics,
    budget: float,
    cycle: int,
    orders: pd.DataFrame | None = None,
) -> PlanResult:
    """Operating business -> Analytics on the real numbers (and uploaded
    orders, if any) -> next period's plan."""
    currency = business.currency
    file_metrics = order_metrics(orders) if orders is not None else None
    segments = None
    if orders is not None:
        table, meta = customer_table(orders)
        segments = segment_summary(table, meta)

    history = [h for h in analytics_history() if h["cycle"] < cycle]
    report = AnalyticsAgent().summarize(cycle, metrics, currency, business.business_summary, history, file_metrics)
    log_decision(
        DecisionRecord(cycle, "analytics", {"metrics": asdict(metrics), "orders_uploaded": orders is not None}, asdict(report))
    )

    sections = {
        "numbers": f"Founder's reported numbers: {describe_period(report.metrics, report.kpis, currency)}",
        "analytics": f"Analytics summary: {report.summary}",
        "budget": f"Budget the founder can deploy next period: {fmt_money(budget, currency)}.",
        "orders": describe_file_metrics(file_metrics, currency) if file_metrics else "",
        "segments": f"Customer groups from the uploaded orders: {describe_segments(segments)}" if segments else "",
    }
    result = _plan(
        cycle,
        EXISTING,
        business,
        sections,
        metrics=metrics,
        budget=budget,
        segments=segments,
        reference_price=file_metrics["average_order_value"] if file_metrics else None,
    )
    result.analytics = report
    return result


# ---------------------------------------------------------------- funding --


def plan_summary(result: PlanResult) -> str:
    s, a, currency = result.strategy, result.allocation, result.brief.currency

    def m(amount):
        return fmt_money(amount, currency)

    split = ", ".join(f"{area} {m(getattr(a, area))}" for area in AREAS if getattr(a, area))
    warnings = " ".join(a.health.get("warnings", []))
    return (
        f"Positioning: {s.positioning}. Target customer: {s.target_customer}. "
        f"Price: {m(s.price)} {s.price_unit}. Budget {m(a.total_budget)} split: {split}. "
        f"{result.product.plan_type.capitalize()} plan total: {m(result.product.line_items_total)}. "
        f"Cash check: {a.health}. {warnings}"
    )


def run_funding(business: BusinessInput, result: PlanResult) -> FundingPlan:
    """Funding roadmap, checked by agents/_guardrails.funding_problems. A
    roadmap that doesn't add up goes back once; anything still wrong after
    that is kept as a visible warning rather than blocking the whole plan."""
    mode = result.brief.mode
    cycle = result.brief.cycle
    summary = plan_summary(result)
    history = analytics_history() if mode == EXISTING else []
    # The traction/revenue comparison assumes a monthly price.
    monthly_price = result.strategy.price if re.search(r"month", result.strategy.price_unit or "", re.IGNORECASE) else None

    agent = FundingAgent()
    feedback = ""
    for attempt in (1, 2):
        plan = agent.assess(business, mode, summary, history, feedback)
        problems = funding_problems(plan, business.currency, monthly_price)
        if not problems:
            break
        log_decision(DecisionRecord(cycle, "funding_rejected", {"attempt": attempt, "problems": problems}, asdict(plan)))
        feedback = "Your previous roadmap was rejected by the checker: " + " ".join(problems) + " Fix these.\n\n"

    plan.warnings = problems
    log_decision(DecisionRecord(cycle, "funding", {"mode": mode, "plan_summary": summary}, asdict(plan)))
    return plan
