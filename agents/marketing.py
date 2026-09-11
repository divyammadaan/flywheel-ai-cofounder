"""Marketing agent — generates ad copy and visuals (multimodal) within its
approved budget. Runs concurrently with Product/Sales/CRM via a CrewAI Flow.
"""

from dataclasses import dataclass


@dataclass
class MarketingOutput:
    cycle: int
    budget_spent: float
    ad_copy: str
    ad_image_path: str | None
    quality_score: float  # 0..1, self-assessed or judged output quality


class MarketingAgent:
    """TODO: wire to crewai.Agent with an image-gen tool (MCP) for ad visuals."""

    def __init__(self, llm_config: dict | None = None):
        self.llm_config = llm_config or {}

    def execute(self, cycle: int, budget: float, positioning: str) -> MarketingOutput:
        # TODO: replace with real CrewAI task execution (copy + image gen).
        return MarketingOutput(
            cycle=cycle,
            budget_spent=budget,
            ad_copy=f"[placeholder ad copy for: {positioning}]",
            ad_image_path=None,
            quality_score=0.5,
        )
