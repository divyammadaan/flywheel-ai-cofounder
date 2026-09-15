"""Funding agent — the funding roadmap: when to target a raise (year and
quarter), at what stage, and the revenue, profit and traction milestones to
hit first.

  launch    no revenue exists yet, so the milestones are targets derived from
            the founder's capital, price and launch plan -- labelled as targets.
  existing  readiness is judged from the founder's real reported numbers, read
            back out of the Analytics Decision Records.

NOTE: investor targeting is by TYPE and profile (e.g. "pre-seed angels in
D2C food, ticket size Rs 25-50 lakh"), not named firms -- the model has no live
access to current fund mandates or portfolio data, and naming specific
investors from stale training data would send founders at the wrong people.

CrewAI + Groq, same pattern as the other agents.
"""

from dataclasses import dataclass
from datetime import date

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._brief import LAUNCH
from agents._models import AGENT_MODELS
from agents._money import fmt_money
from agents._retry import retry_on_rate_limit
from agents.analytics import describe_period
from agents.intake import BusinessInput

DEFAULT_MODEL = AGENT_MODELS["funding"]

_INSTRUCTION = """You are the Funding agent for an AI co-founder platform. You're told today's
date, the business, its current plan, and either that it hasn't launched or its real
reported numbers.

- NOT LAUNCHED: there is no revenue yet. Judge readiness honestly -- most pre-launch
  businesses are not ready to raise. Then lay out the funding roadmap: the year and quarter
  to target a first raise, the stage, and the milestones that must be true first. Ground
  the milestones in the founder's capital, price and plan, and make them numbers in the
  plan currency (e.g. "Rs 8 lakh monthly recurring revenue"), not adjectives. They are
  targets, so call them targets.
- OPERATING: judge readiness from the reported numbers, then give the same roadmap.

Investor targeting: describe the TYPE and profile of investor (stage, ticket size, sector,
geography) -- never name specific funds or people; you have no live data on current mandates.
Pitch deck outline: one short line per slide, specific to this business.

BE CONCISE. No field longer than ~60 words. (Output length is rate-limited, so verbosity
directly costs the founder waiting time.)"""


class FundingSchema(BaseModel):
    readiness: str = Field(description="One of: NOT_READY, READY_PRE_SEED, READY_SEED, READY_SERIES_A")
    readiness_rationale: str = Field(description="2-3 sentences citing the plan or the reported numbers")
    target_raise_date: str = Field(description="When to target the first or next raise, as a quarter and year, e.g. 'Q2 2028'")
    target_stage: str = Field(description="Stage and rough size of the raise, in the plan currency")
    revenue_milestone: str = Field(
        description="Revenue to reach before raising, as a number in the plan currency with its period, e.g. 'Rs 8 lakh monthly recurring revenue'"
    )
    profit_milestone: str = Field(
        description="Profitability to reach first, e.g. 'contribution-margin positive for 6 straight months'"
    )
    traction_milestones: str = Field(description="Customer or traction numbers to reach first")
    investor_profile: str = Field(
        description="Type/profile of investor to target -- stage, ticket size, sector, geography. No named firms."
    )
    alternative_funding: str = Field(
        description="Non-equity options that may fit better right now (revenue-based, grants, bank/MSME loans, bootstrapping)"
    )
    pitch_deck_outline: str = Field(description="Slide-by-slide outline specific to this business")


@dataclass
class FundingPlan:
    mode: str
    currency: str
    readiness: str
    readiness_rationale: str
    target_raise_date: str
    target_stage: str
    revenue_milestone: str
    profit_milestone: str
    traction_milestones: str
    investor_profile: str
    alternative_funding: str
    pitch_deck_outline: str


class FundingAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        llm = LLM(model=model)
        self._agent = Agent(
            role="Funding Advisor",
            goal="Lay out when this business should raise, and what it must achieve first",
            backstory="You've sat on both sides of the table. You tell founders plainly "
            "when they're not ready rather than helping them waste months pitching, you turn "
            "'raise later' into dated, numeric milestones, and you point them at non-equity "
            "options when those genuinely fit better.",
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def assess(
        self, business: BusinessInput, mode: str, plan_summary: str, history: list[dict] | None = None
    ) -> FundingPlan:
        currency = business.currency
        if mode == LAUNCH:
            numbers = (
                "NOT LAUNCHED: no revenue, customers or profit exist yet. "
                f"Founder's capital: {fmt_money(business.starting_capital, currency)}."
            )
        elif history:
            numbers = "OPERATING. Founder's real reported numbers, oldest first:\n" + "\n".join(
                f"- {describe_period(h['metrics'], h['kpis'], currency)}" for h in history
            )
        else:
            numbers = "OPERATING, but no reported numbers are available."

        task = Task(
            description=(
                f"Today's date: {date.today().isoformat()}.\n"
                f"Business: {business.business_summary}\n"
                f"Industry: {business.industry}. Region: {business.target_region}. Currency: {currency}.\n\n"
                f"{numbers}\n\n"
                f"Current plan: {plan_summary}\n\n"
                "Give the funding roadmap."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=FundingSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        p: FundingSchema = task.output.pydantic

        return FundingPlan(
            mode=mode,
            currency=currency,
            readiness=p.readiness,
            readiness_rationale=p.readiness_rationale,
            target_raise_date=p.target_raise_date,
            target_stage=p.target_stage,
            revenue_milestone=p.revenue_milestone,
            profit_milestone=p.profit_milestone,
            traction_milestones=p.traction_milestones,
            investor_profile=p.investor_profile,
            alternative_funding=p.alternative_funding,
            pitch_deck_outline=p.pitch_deck_outline,
        )
