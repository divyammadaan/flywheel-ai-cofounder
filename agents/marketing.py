"""Marketing agent — generates ad copy within its approved budget. Runs
concurrently with Product/Sales/CRM via a CrewAI Flow.

Ad visuals (multimodal) are deliberately out of scope here: image
generation needs its own MCP tool integration, which deserves a focused
build rather than being bolted onto copy generation. ad_image_path stays
None until that pass lands.
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._retry import retry_on_rate_limit

# Groq, not Gemini: Strategy/Finance/Analytics already use Gemini's shared
# 20-req/day free-tier quota (per project, per model) -- keeping the three
# CrewAI execution agents on a different provider avoids all 6 agents
# competing for the same daily cap.
DEFAULT_MODEL = "groq/qwen/qwen3.8-27b"


class MarketingOutputSchema(BaseModel):
    ad_copy: str = Field(description="Ad copy for this cycle, 2-4 sentences")
    quality_score: float = Field(description="Self-assessed quality/confidence 0..1")


@dataclass
class MarketingOutput:
    cycle: int
    budget_spent: float
    ad_copy: str
    ad_image_path: str | None
    quality_score: float


class MarketingAgent:
    """CrewAI agent backed by Groq -- writes ad copy grounded in
    Strategy's positioning, price point, and this cycle's budget."""

    def __init__(self, model: str = DEFAULT_MODEL):
        llm = LLM(model=model)
        self._agent = Agent(
            role="Marketing Lead",
            goal="Write ad copy that converts, grounded in this cycle's positioning and budget",
            backstory=(
                "You run marketing for a lean, fast-moving startup. You write ad copy that "
                "reflects the current positioning and price point, and are honest about your "
                "own confidence in it given the budget you have to work with this cycle."
            ),
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def execute(self, cycle: int, budget: float, positioning: str, pricing: float | None = None) -> MarketingOutput:
        price_context = f" at a ${pricing:.2f} price point" if pricing is not None else ""
        task = Task(
            description=(
                f"Cycle {cycle}. Marketing budget this cycle: ${budget:.2f}. "
                f"Current positioning: {positioning}{price_context}.\n"
                "Write ad copy for this cycle and rate your own confidence in it (0..1), "
                "considering whether the budget supports the reach this copy needs."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=MarketingOutputSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed: MarketingOutputSchema = task.output.pydantic

        return MarketingOutput(
            cycle=cycle,
            budget_spent=budget,
            ad_copy=parsed.ad_copy,
            ad_image_path=None,
            quality_score=parsed.quality_score,
        )
