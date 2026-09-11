"""Analytics agent — aggregates all agent + simulator output into KPIs and a
natural-language summary that becomes next cycle's Strategy input, closing
the loop.

Built on Google ADK for session/memory: needs cross-cycle KPI history to
describe trends, not just single-cycle snapshots.
"""

from dataclasses import dataclass

from simulator.market_simulator import SimulationResult


@dataclass
class AnalyticsReport:
    cycle: int
    revenue: float
    conversion_rate: float
    cac: float
    churn_rate: float
    summary: str


class AnalyticsAgent:
    """TODO: wire to google-adk Agent for LLM-generated NL summaries with
    cross-cycle trend awareness. Numeric aggregation below is plain Python
    and doesn't need an LLM."""

    def __init__(self, llm_config: dict | None = None):
        self.llm_config = llm_config or {}

    def summarize(self, cycle: int, sim_result: SimulationResult, leads: int) -> AnalyticsReport:
        conversion_rate = (sim_result.conversions / leads) if leads else 0.0
        # TODO: replace templated summary with an LLM-generated one via ADK.
        summary = (
            f"Cycle {cycle}: {sim_result.conversions} conversions from {leads} leads "
            f"({conversion_rate:.1%} conversion), revenue ${sim_result.revenue:.2f}, "
            f"CAC ${sim_result.cac:.2f}, churn {sim_result.churn_rate:.1%}."
        )
        if sim_result.shock_applied:
            summary += f" Market shock this cycle: {sim_result.shock_applied}."

        return AnalyticsReport(
            cycle=cycle,
            revenue=sim_result.revenue,
            conversion_rate=round(conversion_rate, 4),
            cac=sim_result.cac,
            churn_rate=sim_result.churn_rate,
            summary=summary,
        )
