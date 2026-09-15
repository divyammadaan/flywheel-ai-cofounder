"""Sales agent — says exactly where leads will come from and how, with a
weekly cadence and a spend per source, plus the steps that turn a lead into
a paying customer. Runs concurrently with Marketing/Product/CRM.

Lead-source budgets are checked in code (agents/_money.fit_to_budget), the
same way as Marketing's campaigns.
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._brief import LAUNCH, PlanBrief
from agents._models import AGENT_MODELS
from agents._money import fit_to_budget
from agents._retry import retry_on_rate_limit

DEFAULT_MODEL = AGENT_MODELS["sales"]


class LeadSource(BaseModel):
    where: str = Field(
        description="Exactly where these leads come from, e.g. 'resident WhatsApp groups in HSR Layout apartments'"
    )
    how: str = Field(description="How to get them, in one or two sentences")
    weekly_actions: str = Field(
        description="A concrete weekly cadence, e.g. '2 sampling stalls each weekend, 40 follow-up calls'"
    )
    budget: float = Field(description="Spend on this source, in the plan currency")


class SalesOutputSchema(BaseModel):
    lead_sources: list[LeadSource] = Field(
        description="2-4 lead sources whose budgets add up to no more than the sales budget"
    )
    conversion_process: str = Field(description="The numbered steps that turn a lead into a paying customer")


@dataclass
class SalesOutput:
    cycle: int
    budget: float
    currency: str
    lead_sources: list
    conversion_process: str
    budget_adjusted: bool = False


class SalesAgent:
    """CrewAI agent backed by Groq -- where and how leads come from, and how
    they become customers, grounded in the shared PlanBrief."""

    def __init__(self, model: str = DEFAULT_MODEL):
        llm = LLM(model=model)
        self._agent = Agent(
            role="Sales Lead",
            goal="Say exactly where and how the business gets its leads, and how they become customers",
            backstory=(
                "You run sales for a lean startup. You name real places to find buyers -- specific "
                "communities, localities, platforms and partner businesses -- and a cadence someone "
                "could start following on Monday morning. Never generic advice like 'do outreach'."
            ),
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def execute(self, brief: PlanBrief, budget: float) -> SalesOutput:
        if brief.mode == LAUNCH:
            focus = "Before launch there are no leads yet: plan how to build the first pipeline."
        else:
            focus = "Use the reported numbers to decide which lead sources to push and which to cut."
        task = Task(
            description=(
                f"{brief.describe(budget, 'Sales budget')}\n\n"
                f"{focus}\n"
                "Give 2-4 specific lead sources and the lead-to-customer steps. "
                "BE CONCISE: keep every field under ~25 words."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=SalesOutputSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed: SalesOutputSchema = task.output.pydantic

        sources = [s.model_dump() for s in parsed.lead_sources]
        fitted, adjusted = fit_to_budget([s["budget"] for s in sources], budget)
        for source, amount in zip(sources, fitted):
            source["budget"] = amount

        return SalesOutput(
            cycle=brief.cycle,
            budget=budget,
            currency=brief.currency,
            lead_sources=sources,
            conversion_process=parsed.conversion_process,
            budget_adjusted=adjusted,
        )
