"""Product agent — decides one concrete product/storefront change per cycle
and self-assesses its quality. Runs concurrently with Marketing/Sales/CRM
via a CrewAI Flow.

Actually shipping a live, deployable storefront (the README's "Live Product
artifact" feature) is separate, larger scope -- this agent's job here is
the LLM-backed decision of what to build and why, grounded in positioning
and budget.
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


class ProductOutputSchema(BaseModel):
    change_description: str = Field(description="One concrete product/storefront change for this cycle")
    quality_score: float = Field(description="Self-assessed quality/confidence 0..1 given the budget")


@dataclass
class ProductOutput:
    cycle: int
    budget_spent: float
    change_description: str
    quality_score: float


class ProductAgent:
    """CrewAI agent backed by Groq -- decides one concrete product change
    per cycle, grounded in positioning and budget."""

    def __init__(self, model: str = DEFAULT_MODEL):
        llm = LLM(model=model)
        self._agent = Agent(
            role="Product Lead",
            goal="Ship one concrete, high-leverage product/storefront change per cycle",
            backstory=(
                "You run product for a lean startup. Each cycle you pick one concrete change "
                "to the storefront or product that best serves the current positioning, given "
                "a limited budget -- and you're honest about how much you could actually get "
                "done with that budget."
            ),
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def execute(self, cycle: int, budget: float, positioning: str | None = None) -> ProductOutput:
        context = f" Current positioning: {positioning}." if positioning else ""
        task = Task(
            description=(
                f"Cycle {cycle}. Product budget this cycle: ${budget:.2f}.{context}\n"
                "Describe one concrete product/storefront change to make this cycle and rate "
                "your confidence (0..1) in shipping it well given the budget."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=ProductOutputSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed: ProductOutputSchema = task.output.pydantic

        return ProductOutput(
            cycle=cycle,
            budget_spent=budget,
            change_description=parsed.change_description,
            quality_score=parsed.quality_score,
        )
