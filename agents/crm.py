"""CRM agent — tracks customer interactions/segments, flags churn signals.
Runs concurrently with Marketing/Product/Sales via a CrewAI Flow.

Phase 2+ extension (not part of the initial 5-agent thin slice).
"""

from dataclasses import dataclass


@dataclass
class CRMOutput:
    cycle: int
    budget_spent: float
    retention_effort: float  # 0..1
    at_risk_segments: list


class CRMAgent:
    """TODO: wire to crewai.Agent."""

    def __init__(self, llm_config: dict | None = None):
        self.llm_config = llm_config or {}

    def execute(self, cycle: int, budget: float) -> CRMOutput:
        return CRMOutput(cycle=cycle, budget_spent=budget, retention_effort=0.5, at_risk_segments=[])
