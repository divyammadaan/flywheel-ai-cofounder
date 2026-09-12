"""Sales agent — handles simulated inbound leads, drafts outreach, closes
simulated deals. Runs concurrently with Marketing/Product/CRM via a CrewAI
Flow.

Note: within a cycle, execution agents act BEFORE the Market Simulator
runs, so `leads` here means leads carried over from the PRIOR cycle's
simulation (0 on cycle 1) -- this cycle's own leads don't exist yet.
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._models import AGENT_MODELS
from agents._retry import retry_on_rate_limit

# Groq, not Gemini: Strategy/Finance/Analytics already use Gemini's shared
# 20-req/day free-tier quota (per project, per model) -- keeping the three
# CrewAI execution agents on a different provider avoids all 6 agents
# competing for the same daily cap.
DEFAULT_MODEL = AGENT_MODELS["sales"]


class SalesOutputSchema(BaseModel):
    outreach_effort: float = Field(description="0..1 outreach effort/intensity for this cycle")
    approach: str = Field(description="1-2 sentence outreach approach for this cycle")


@dataclass
class SalesOutput:
    cycle: int
    budget_spent: float
    outreach_effort: float


class SalesAgent:
    """CrewAI agent backed by Groq -- decides outreach effort/approach
    given budget and leads carried over from the prior cycle."""

    def __init__(self, model: str = DEFAULT_MODEL):
        llm = LLM(model=model)
        self._agent = Agent(
            role="Sales Lead",
            goal="Convert available leads into deals within budget",
            backstory=(
                "You run sales for a lean startup. Each cycle you decide how much outreach "
                "effort to put in and what approach to take, given your budget and how many "
                "leads you have to work with."
            ),
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def execute(self, cycle: int, budget: float, leads: int) -> SalesOutput:
        task = Task(
            description=(
                f"Cycle {cycle}. Sales budget this cycle: ${budget:.2f}. "
                f"Leads available from last cycle: {leads}.\n"
                "Decide your outreach effort (0..1) and describe your approach this cycle."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=SalesOutputSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed: SalesOutputSchema = task.output.pydantic

        return SalesOutput(cycle=cycle, budget_spent=budget, outreach_effort=parsed.outreach_effort)
