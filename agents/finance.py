"""Finance agent — allocates a fixed shared budget across the execution
agents based on Strategy's priorities, enforcing hard spend caps (guardrail).

Built on Google ADK: needs session memory of past allocations vs. outcomes
to negotiate better next time.
"""

from dataclasses import dataclass

# Guardrail: no single agent may receive more than this fraction of budget.
MAX_SHARE_PER_AGENT = 0.6


@dataclass
class BudgetAllocation:
    cycle: int
    total_budget: float
    marketing: float
    product: float
    sales: float
    crm: float

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
            if amount > self.total_budget * MAX_SHARE_PER_AGENT:
                raise ValueError(f"{name} allocation {amount} exceeds guardrail cap")


class FinanceAgent:
    """TODO: wire to google-adk Agent; for now allocates proportionally to
    Strategy's stated priorities within the hard caps."""

    def __init__(self, total_budget_per_cycle: float, llm_config: dict | None = None):
        self.total_budget_per_cycle = total_budget_per_cycle
        self.llm_config = llm_config or {}

    def allocate(self, cycle: int, priorities: dict) -> BudgetAllocation:
        total = sum(priorities.values()) or 1.0
        normalized = {k: v / total for k, v in priorities.items()}

        def capped(share: float) -> float:
            return min(share, MAX_SHARE_PER_AGENT) * self.total_budget_per_cycle

        return BudgetAllocation(
            cycle=cycle,
            total_budget=self.total_budget_per_cycle,
            marketing=round(capped(normalized.get("marketing", 0)), 2),
            product=round(capped(normalized.get("product", 0)), 2),
            sales=round(capped(normalized.get("sales", 0)), 2),
            crm=round(capped(normalized.get("crm", 0)), 2),
        )
