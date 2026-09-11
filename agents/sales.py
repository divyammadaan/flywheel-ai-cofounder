"""Sales agent — handles simulated inbound leads, drafts outreach, closes
simulated deals. Runs concurrently with Marketing/Product/CRM via a CrewAI Flow.
"""

from dataclasses import dataclass


@dataclass
class SalesOutput:
    cycle: int
    budget_spent: float
    outreach_effort: float  # 0..1


class SalesAgent:
    """TODO: wire to crewai.Agent."""

    def __init__(self, llm_config: dict | None = None):
        self.llm_config = llm_config or {}

    def execute(self, cycle: int, budget: float, leads: int) -> SalesOutput:
        # TODO: replace with real CrewAI task execution over `leads`.
        return SalesOutput(cycle=cycle, budget_spent=budget, outreach_effort=0.5)
