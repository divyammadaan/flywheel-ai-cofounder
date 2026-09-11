"""Rule-based market simulator — converts one cycle's execution output into
synthetic demand/conversion events. Deterministic given a seed, so runs are
reproducible; NOT an LLM by design (keeps the loop free and fast to run).
"""

import math
import random
from dataclasses import dataclass


@dataclass
class ExecutionOutput:
    """What the execution agents produced this cycle."""
    marketing_spend: float
    marketing_quality: float  # 0..1, e.g. ad copy/visual quality score
    product_quality: float  # 0..1, current product/storefront quality
    sales_effort: float  # 0..1, outreach volume/quality this cycle
    crm_retention_effort: float  # 0..1, churn-prevention effort this cycle


@dataclass
class SimulationResult:
    leads_generated: int
    conversions: int
    revenue: float
    churn_rate: float
    cac: float  # customer acquisition cost
    shock_applied: str | None


def _diminishing_returns(spend: float, scale: float = 500.0) -> float:
    """Classic diminishing-returns curve: more spend helps, but less per dollar."""
    if spend <= 0:
        return 0.0
    return math.log1p(spend / scale)


class MarketSimulator:
    """Seeded, reproducible rule-based simulator with noise + shocks."""

    SHOCK_PROBABILITY = 0.1
    SHOCKS = {
        "demand_spike": 1.4,
        "demand_slump": 0.6,
        "viral_moment": 1.8,
    }

    def __init__(self, seed: int, existing_customers: int = 0):
        self.rng = random.Random(seed)
        self.existing_customers = existing_customers

    def _maybe_apply_shock(self, base_demand: float) -> tuple[float, str | None]:
        if self.rng.random() < self.SHOCK_PROBABILITY:
            shock = self.rng.choice(list(self.SHOCKS))
            return base_demand * self.SHOCKS[shock], shock
        return base_demand, None

    def run_cycle(self, execution: ExecutionOutput) -> SimulationResult:
        # base demand from marketing reach x quality, with diminishing returns on spend
        reach = _diminishing_returns(execution.marketing_spend)
        base_demand = reach * (0.3 + 0.7 * execution.marketing_quality)

        demand, shock = self._maybe_apply_shock(base_demand)
        noise = self.rng.uniform(0.9, 1.1)
        leads = max(0, round(demand * 25 * noise))

        # conversion depends on product quality + sales effort, product matters more
        conv_rate = min(0.95, 0.05 + 0.35 * execution.product_quality + 0.15 * execution.sales_effort)
        conv_rate *= self.rng.uniform(0.9, 1.1)
        conversions = round(leads * conv_rate)

        avg_deal_size = 40.0 * (0.6 + 0.4 * execution.product_quality)
        revenue = conversions * avg_deal_size

        cac = (execution.marketing_spend / conversions) if conversions else float("inf")

        # churn falls with CRM effort, has a floor
        churn_rate = max(0.02, 0.20 - 0.15 * execution.crm_retention_effort)
        churn_rate *= self.rng.uniform(0.9, 1.1)

        return SimulationResult(
            leads_generated=leads,
            conversions=conversions,
            revenue=round(revenue, 2),
            churn_rate=round(churn_rate, 4),
            cac=round(cac, 2) if conversions else -1.0,
            shock_applied=shock,
        )
