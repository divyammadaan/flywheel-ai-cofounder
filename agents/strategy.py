"""Strategy agent — reads last cycle's Analytics summary and revises the
business plan (positioning, pricing, priorities) for the next cycle.

Built on Google ADK for session/memory: needs to remember prior cycles'
decisions and outcomes to reason about what to change.
"""

from dataclasses import dataclass


@dataclass
class StrategyDecision:
    cycle: int
    positioning: str
    pricing: float
    priorities: dict  # e.g. {"marketing": 0.4, "product": 0.3, "sales": 0.2, "crm": 0.1}
    rationale: str


class StrategyAgent:
    """TODO: wire to google-adk Agent with session state carrying prior
    cycles' StrategyDecision + Analytics summaries."""

    def __init__(self, llm_config: dict | None = None):
        self.llm_config = llm_config or {}

    def decide(self, cycle: int, previous_analytics_summary: str | None) -> StrategyDecision:
        # TODO: replace with ADK-backed LLM call once Ollama/Groq wiring is in.
        if previous_analytics_summary is None:
            return StrategyDecision(
                cycle=cycle,
                positioning="initial launch positioning",
                pricing=40.0,
                priorities={"marketing": 0.4, "product": 0.3, "sales": 0.2, "crm": 0.1},
                rationale="No prior data yet; default balanced allocation to seed the loop.",
            )
        raise NotImplementedError("LLM-backed strategy revision not yet wired")
