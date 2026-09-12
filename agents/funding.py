"""Funding agent — decides whether the business should raise now, and if
not now, what has to be true first. On a "raise" call it also produces the
investor targeting profile and a pitch deck outline.

Takes the engine's actual KPI history as input, so "you're not ready yet"
is grounded in the business's real measured performance (revenue, CAC,
churn trajectory) rather than vibes.

NOTE: investor targeting is by TYPE and profile (e.g. "pre-seed angels in
D2C food, ticket size $25-50k"), not named firms -- the model has no live
access to current fund mandates or portfolio data, and naming specific
investors from stale training data would send founders at the wrong people.

CrewAI + Groq, same pattern as the other agents.
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._models import GROQ_MODEL
from agents._retry import retry_on_rate_limit
from agents.intake import BusinessInput

DEFAULT_MODEL = GROQ_MODEL

_INSTRUCTION = """You are the Funding agent for an AI co-founder platform. Given a business,
its region, and its actual measured KPI history from the execution engine, decide whether
it should raise external capital now.

Be honest and specific. "Not yet" is the right answer for most early businesses -- if so,
say exactly which metrics need to move and to roughly what level before investors will
take a meeting, and estimate how many cycles/months that might take.

For investor targeting, describe the TYPE and profile of investor that fits (stage, ticket
size, sector focus, geography) -- do NOT name specific funds or individuals, since you
have no live access to current fund mandates and would likely be out of date.

The pitch deck outline should be slide-by-slide and specific to THIS business, not a
generic template -- reference their actual numbers and positioning.

BE CONCISE. Every field is capped: no field longer than ~60 words, and the deck outline is
one short line per slide. Dense and specific beats long -- cut hedging, preamble and
restatement, not substance. (Output length is rate-limited, so verbosity directly costs
the founder waiting time.)"""


class FundingSchema(BaseModel):
    readiness: str = Field(description="One of: NOT_READY, READY_PRE_SEED, READY_SEED, READY_SERIES_A")
    readiness_rationale: str = Field(description="2-3 sentences citing the actual KPIs")
    recommended_timing: str = Field(description="When to raise, and what must be true first")
    metrics_to_hit: str = Field(description="Specific metric targets to reach before raising")
    investor_profile: str = Field(description="Type/profile of investor to target -- stage, ticket size, sector, geography. No named firms.")
    alternative_funding: str = Field(description="Non-equity options that may fit better right now (revenue-based, grants, bank/MSME loans, bootstrapping)")
    pitch_deck_outline: str = Field(description="Slide-by-slide outline specific to this business")


@dataclass
class FundingPlan:
    readiness: str
    readiness_rationale: str
    recommended_timing: str
    metrics_to_hit: str
    investor_profile: str
    alternative_funding: str
    pitch_deck_outline: str


class FundingAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        llm = LLM(model=model, response_format=FundingSchema)
        self._agent = Agent(
            role="Funding Advisor",
            goal="Decide if this business should raise now, and prepare it if so",
            backstory="You've sat on both sides of the table. You tell founders plainly "
            "when they're not ready rather than helping them waste months pitching, and you "
            "point them at non-equity options when those genuinely fit better.",
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def assess(self, business: BusinessInput, kpi_history: list[dict]) -> FundingPlan:
        if kpi_history:
            kpi_text = "\n".join(
                f"Cycle {k['cycle']}: revenue ${k['revenue']:.2f}, conversion {k['conversion_rate']:.0%}, "
                f"CAC ${k['cac']:.2f}, churn {k['churn_rate']:.1%}"
                for k in kpi_history
            )
        else:
            kpi_text = "No cycles have run yet -- no measured performance data exists."

        existing = f"\nExisting business financials: {business.existing_metrics}." if business.existing_metrics else ""

        task = Task(
            description=(
                f"Business: {business.business_summary}\n"
                f"Industry: {business.industry}. Region: {business.target_region}.{existing}\n\n"
                f"Measured KPI history from the execution engine:\n{kpi_text}\n\n"
                "Give your funding assessment."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=FundingSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        p: FundingSchema = task.output.pydantic

        return FundingPlan(
            readiness=p.readiness,
            readiness_rationale=p.readiness_rationale,
            recommended_timing=p.recommended_timing,
            metrics_to_hit=p.metrics_to_hit,
            investor_profile=p.investor_profile,
            alternative_funding=p.alternative_funding,
            pitch_deck_outline=p.pitch_deck_outline,
        )
