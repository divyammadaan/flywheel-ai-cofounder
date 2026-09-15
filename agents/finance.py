"""Finance agent — the money math behind every plan.

  launch    how much of the founder's capital can go into the launch once a
            reserve for running costs is held back, and what break-even takes
            (units a month whose margin covers fixed costs).
  existing  runway at the current profit or loss, debt against a year of
            revenue, and whether next period's budget fits the cash in the bank.

Then it splits the spendable budget across the planning areas based on
Strategy's priorities, with a hard per-area cap, and explains the result.

This agent makes no model call. Everything it produces is arithmetic
(agents/_cash.py, compute_capped_allocation) -- a guardrail must hold even if
a model's reasoning is wrong -- and the explanation only restates those
numbers, so it is written from them in code too. An LLM used to write that
explanation; it added a call per run and couldn't add anything the numbers
didn't already say.
"""

from dataclasses import dataclass, field

from agents._cash import launch_cash_plan, operating_cash_position
from agents._money import fmt_money
from agents.analytics import PeriodMetrics

# Guardrail: no single area may receive more than this fraction of budget.
MAX_SHARE_PER_AGENT = 0.6


def compute_capped_allocation(total_budget: float, priorities: dict) -> dict:
    """Pure, deterministic guardrail logic: normalize priorities, cap each
    area's share at MAX_SHARE_PER_AGENT. No LLM involved, so this is unit
    tested directly and always holds regardless of what any agent proposes.
    """
    total = sum(priorities.values()) or 1.0
    normalized = {k: v / total for k, v in priorities.items()}

    def capped(share: float) -> float:
        return min(share, MAX_SHARE_PER_AGENT) * total_budget

    return {
        "marketing": round(capped(normalized.get("marketing", 0)), 2),
        "product": round(capped(normalized.get("product", 0)), 2),
        "sales": round(capped(normalized.get("sales", 0)), 2),
        "crm": round(capped(normalized.get("crm", 0)), 2),
    }


def _area_label(area: str) -> str:
    return "CRM" if area == "crm" else area


def _main_cash_risk(health: dict, currency: str) -> str:
    if health.get("warnings"):
        return health["warnings"][0]
    if health.get("break_even_units_per_month") is not None:
        return (
            f"Break-even needs {health['break_even_units_per_month']:,} units a month at "
            f"{fmt_money(health.get('contribution_margin'), currency)} margin each."
        )
    if "profitable" in health:
        if health["profitable"]:
            return "The business is profitable, so there is no monthly cash burn."
        if health.get("runway_months"):
            return f"At the current loss, cash lasts about {health['runway_months']} months."
    return ""


def explain_allocation(total_budget: float, priorities: dict, amounts: dict, health: dict, currency: str) -> str:
    """The allocation and its biggest cash risk in plain words, from the numbers alone."""
    spent = sorted(((area, amount) for area, amount in amounts.items() if amount), key=lambda item: -item[1])
    if not total_budget or not spent:
        sentences = ["There is no budget to split."]
    else:
        split = ", ".join(
            f"{_area_label(area)} {fmt_money(amount, currency)} ({amount / total_budget:.0%})" for area, amount in spent
        )
        sentences = [f"{fmt_money(total_budget, currency)} split by Strategy's priorities: {split}."]

    requested = sum(priorities.values()) or 1.0
    capped = [_area_label(area) for area, weight in priorities.items() if weight / requested > MAX_SHARE_PER_AGENT]
    if capped and total_budget:
        left = total_budget - sum(amounts.values())
        sentences.append(
            f"{' and '.join(capped).capitalize()} asked for more than {MAX_SHARE_PER_AGENT:.0%} of the budget "
            f"and was capped, leaving {fmt_money(left, currency)} unallocated."
        )

    risk = _main_cash_risk(health, currency)
    if risk:
        sentences.append(risk)
    return " ".join(sentences)


@dataclass
class BudgetAllocation:
    cycle: int
    total_budget: float
    marketing: float
    product: float
    sales: float
    crm: float
    rationale: str = ""
    currency: str = "INR"
    # The cash check from agents/_cash.py this allocation was based on.
    health: dict = field(default_factory=dict)

    def __post_init__(self):
        allocated = self.marketing + self.product + self.sales + self.crm
        if allocated > self.total_budget + 1e-6:
            raise ValueError(f"Allocation {allocated} exceeds total budget {self.total_budget}")
        for name, amount in (
            ("marketing", self.marketing),
            ("product", self.product),
            ("sales", self.sales),
            ("crm", self.crm),
        ):
            if amount > self.total_budget * MAX_SHARE_PER_AGENT + 1e-6:
                raise ValueError(f"{name} allocation {amount} exceeds guardrail cap")


class FinanceAgent:
    """Cash math, guardrail-enforced allocation and its explanation -- all code."""

    def __init__(self, currency: str):
        self.currency = currency

    def plan_launch(
        self,
        cycle: int,
        priorities: dict,
        capital: float,
        price: float,
        monthly_fixed_costs: float | None,
        unit_cost: float | None,
        runway_months: int,
    ) -> BudgetAllocation:
        health = launch_cash_plan(capital, price, monthly_fixed_costs, unit_cost, runway_months)
        return self.allocate(cycle, priorities, health["launch_budget"], health)

    def plan_operating(self, cycle: int, priorities: dict, metrics: PeriodMetrics, budget: float) -> BudgetAllocation:
        health = operating_cash_position(
            metrics.revenue, metrics.net_profit, metrics.total_debt, budget, metrics.period_months, metrics.cash_in_bank
        )
        return self.allocate(cycle, priorities, budget, health)

    def allocate(self, cycle: int, priorities: dict, total_budget: float, health: dict) -> BudgetAllocation:
        amounts = compute_capped_allocation(total_budget, priorities)
        return BudgetAllocation(
            cycle=cycle,
            total_budget=total_budget,
            rationale=explain_allocation(total_budget, priorities, amounts, health, self.currency),
            currency=self.currency,
            health=health,
            **amounts,
        )
