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

What is deliberately NOT here:
  - The market simulator. simulator/market_simulator.py and its tests still
    exist but aren't wired in: made-up revenue for a business that hasn't
    launched was misleading.
  - A hardcoded budget. Every amount is the founder's own figure.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

import pandas as pd

from agents._brief import EXISTING, LAUNCH, OFFERING_LABELS, PlanBrief
from agents._guardrails import strategy_problems
from agents._money import fmt_money
from agents._segments import customer_table, describe_segments, segment_summary
from agents.analytics import AnalyticsAgent, AnalyticsReport, PeriodMetrics, describe_period
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
    context: str,
    metrics: PeriodMetrics | None = None,
    budget: float | None = None,
    segments: dict | None = None,
    reference_price: float | None = None,
) -> PlanResult:
    currency = business.currency
    areas = planning_areas(mode, segments is not None)
    context = f"{context}\nBudget areas this period: {', '.join(areas)}."

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

    brief = PlanBrief(
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
        context=context,
        offering_type=business.offering_type,
    )

    # The planning agents are independent: each needs only the shared brief
    # and its own slice of the budget, and none reads another's output.
    # Running them concurrently makes this stage as slow as the slowest agent
    # rather than the sum of all of them.
    #
    # Marketing goes through request_marketing(), which routes over A2A when
    # the bridge server is running (see orchestration/a2a_bridge.py) and
    # falls back to an in-process call otherwise.
    with ThreadPoolExecutor(max_workers=len(areas)) as pool:
        futures = {
            "marketing": pool.submit(request_marketing, brief, allocation.marketing),
            "product": pool.submit(ProductAgent().execute, brief, allocation.product),
            "sales": pool.submit(SalesAgent().execute, brief, allocation.sales),
        }
        if "crm" in areas:
            futures["crm"] = pool.submit(CRMAgent().execute, brief, allocation.crm, segments, previous_segments(cycle))
        # .result() re-raises in the caller, so a failing agent still surfaces
        # rather than being silently swallowed by the pool.
        marketing, transport = futures["marketing"].result()
        outputs = {name: f.result() for name, f in futures.items() if name != "marketing"}

    logged = {"marketing": marketing, **outputs}
    for name, out in logged.items():
        snapshot = {"budget": getattr(allocation, name), "brief": asdict(brief)}
        # Record which transport Marketing used, so the Decision Record shows
        # whether A2A was actually exercised rather than leaving it ambiguous
        # after a silent fallback.
        if name == "marketing":
            snapshot["transport"] = transport
        log_decision(DecisionRecord(cycle, name, snapshot, asdict(out)))

    return PlanResult(
        brief, strategy, allocation, marketing, transport, outputs["product"], outputs["sales"], outputs.get("crm")
    )


# ------------------------------------------------------------- new idea --


def launch_context(
    business: BusinessInput,
    research: MarketResearchReport,
    decision: AdvisorDecision,
    qa_answers: dict[str, str] | None = None,
) -> str:
    currency = business.currency
    answers = "\n".join(f"- Q: {q} A: {a}" for q, a in (qa_answers or {}).items()) or "- none"
    costs = (
        f"Founder's monthly fixed costs: {fmt_money(business.monthly_fixed_costs, currency)}; "
        f"cost to deliver one unit: {fmt_money(business.unit_cost, currency)} ('—' means not given)."
    )
    return (
        f"Founder's capital for the launch: {fmt_money(business.starting_capital, currency)}. {costs}\n"
        f"Market research (estimates, no live data): size {research.market_size_estimate} "
        f"Competitors: {research.key_competitors} Opportunities: {research.opportunities} "
        f"Risks: {research.risks}\n"
        f"Founder's answers:\n{answers}\n"
        f"Founder Advisor verdict: {decision.verdict} -- {decision.rationale}\n"
        f"Advisor's seed plan: positioning '{decision.seed_positioning}', price "
        f"{fmt_money(decision.seed_price, currency)} {decision.seed_price_unit}, "
        f"budget priorities {decision.seed_priorities}."
    )


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
        launch_context(business, research, decision, qa_answers),
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

    context = (
        f"Founder's reported numbers: {describe_period(report.metrics, report.kpis, currency)}\n"
        f"Analytics summary: {report.summary}\n"
        f"Budget the founder can deploy next period: {fmt_money(budget, currency)}."
    )
    if segments:
        context += f"\nCustomer groups from the uploaded orders: {describe_segments(segments)}"

    result = _plan(
        cycle,
        EXISTING,
        business,
        context,
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
    mode = result.brief.mode
    summary = plan_summary(result)
    history = analytics_history() if mode == EXISTING else []
    plan = FundingAgent().assess(business, mode, summary, history)
    log_decision(DecisionRecord(result.brief.cycle, "funding", {"mode": mode, "plan_summary": summary}, asdict(plan)))
    return plan
