"""Product agent — writes, tests, and ships a real, deployable change to the
storefront/landing page each cycle. Runs concurrently with Marketing/Sales/CRM
via a CrewAI Flow.

Phase 2+ extension (not part of the initial 5-agent thin slice).
"""

from dataclasses import dataclass


@dataclass
class ProductOutput:
    cycle: int
    budget_spent: float
    change_description: str
    quality_score: float  # 0..1


class ProductAgent:
    """TODO: wire to crewai.Agent with a code-edit/deploy tool (MCP)."""

    def __init__(self, llm_config: dict | None = None):
        self.llm_config = llm_config or {}

    def execute(self, cycle: int, budget: float) -> ProductOutput:
        return ProductOutput(
            cycle=cycle,
            budget_spent=budget,
            change_description="[placeholder product change]",
            quality_score=0.5,
        )
