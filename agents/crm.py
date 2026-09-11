"""CRM agent — tracks customer interactions/segments, flags churn signals.
Runs concurrently with Marketing/Product/Sales via a CrewAI Flow.

Deliberately runs on a local Ollama model (qwen3:4b), not a hosted API:
customer interaction/churn data is the most privacy-sensitive slice of
Flywheel, so this agent's inputs and outputs never leave the machine.
Satisfies the course's local-LLM / data-privacy requirement (CO2).
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

OLLAMA_MODEL = "ollama/qwen3:4b"
OLLAMA_BASE_URL = "http://localhost:11434"


class CRMOutputSchema(BaseModel):
    retention_effort: float = Field(description="0..1 recommended retention effort for this cycle")
    at_risk_segments: list[str] = Field(description="Short labels for customer segments at churn risk")
    reasoning: str = Field(description="1-2 sentence justification")


@dataclass
class CRMOutput:
    cycle: int
    budget_spent: float
    retention_effort: float
    at_risk_segments: list


class CRMAgent:
    """CrewAI agent backed by local Ollama -- customer data never leaves
    this machine, by design."""

    def __init__(self, model: str = OLLAMA_MODEL, base_url: str = OLLAMA_BASE_URL):
        llm = LLM(model=model, base_url=base_url)
        self._agent = Agent(
            role="CRM Manager",
            goal="Track customer interactions and flag churn-risk segments each cycle",
            backstory=(
                "You manage customer relationships for a lean startup. You watch engagement "
                "signals and recommend how much retention effort (0..1) the team should invest "
                "this cycle, and which customer segments look most at risk of churning."
            ),
            llm=llm,
            verbose=False,
        )

    def execute(self, cycle: int, budget: float, previous_churn_rate: float | None = None) -> CRMOutput:
        churn_context = (
            f"Last measured churn rate: {previous_churn_rate:.1%}."
            if previous_churn_rate is not None
            else "No churn data yet -- this is the first cycle."
        )
        task = Task(
            description=(
                f"Cycle {cycle}. CRM budget this cycle: ${budget:.2f}. {churn_context}\n"
                "Recommend a retention_effort (0..1) and list any at-risk customer segments."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=CRMOutputSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed: CRMOutputSchema = task.output.pydantic

        return CRMOutput(
            cycle=cycle,
            budget_spent=budget,
            retention_effort=parsed.retention_effort,
            at_risk_segments=parsed.at_risk_segments,
        )
