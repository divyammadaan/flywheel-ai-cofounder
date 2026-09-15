"""Intake agent — the front door. Takes a founder's raw pitch (new idea) or
existing-business description and normalizes it into a structured
BusinessInput that the other agents reason over.

It also classifies what the business delivers (physical goods, a service, or
software), which decides whether Product plans inventory or delivery capacity.

CrewAI + Groq, same pattern as Marketing/Product/Sales.
"""

import re
from dataclasses import dataclass, field

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._cache import cached
from agents._cash import DEFAULT_RUNWAY_MONTHS
from agents._models import AGENT_MAX_TOKENS, AGENT_MODELS
from agents._retry import retry_on_rate_limit
from observability.usage import register_role

DEFAULT_MODEL = AGENT_MODELS["intake"]
OFFERING_TYPES = ("physical", "service", "software")

_INSTRUCTION = """You are the Intake agent for an AI co-founder platform. A founder gives you
either a raw pitch for a new business idea, or a description of an existing business
(with financials). Extract a clean, structured summary from whatever they gave you.

If they described a NEW idea: infer industry and product_or_service from the pitch. Leave
existing_* fields as null/0 -- there's no business yet.

If they described an EXISTING business: extract whatever financial figures they mentioned
(revenue, PAT, EBITDA, debt) -- use 0 for anything not mentioned, don't invent numbers.

target_region: use what they said; if truly unspecified, write "unspecified" rather than
guessing a country.

offering_type: "physical" if they sell physical goods (food, clothing, hardware),
"service" if they sell work done for customers (salon, agency, tutoring, repairs),
"software" if they sell an app, SaaS or other digital product."""


class IntakeOutputSchema(BaseModel):
    mode: str = Field(description="Either 'new_idea' or 'existing_business'")
    business_summary: str = Field(description="1-2 sentence clean summary of the business")
    industry: str = Field(description="e.g. 'e-commerce', 'fintech', 'D2C footwear'")
    product_or_service: str = Field(description="What they actually sell/build")
    offering_type: str = Field(description="One of: physical, service, software")
    target_region: str = Field(description="Region/country/market they're targeting, or 'unspecified'")
    existing_revenue: float = Field(default=0.0, description="Annual revenue if existing business, else 0")
    existing_pat: float = Field(default=0.0, description="Profit after tax if existing business, else 0")
    existing_ebitda: float = Field(default=0.0, description="EBITDA if existing business, else 0")
    existing_debt: float = Field(default=0.0, description="Outstanding debt if existing business, else 0")


@dataclass
class BusinessInput:
    mode: str
    business_summary: str
    industry: str
    product_or_service: str
    target_region: str
    existing_metrics: dict = field(default_factory=dict)
    raw_input: str = ""
    # Everything below is set from the founder's own input (dashboard/CLI),
    # never extracted by the model: budgets and costs must be numbers the
    # founder actually gave.
    currency: str = "INR"
    starting_capital: float = 0.0
    offering_type: str = "physical"
    monthly_fixed_costs: float | None = None
    unit_cost: float | None = None
    runway_months: int = DEFAULT_RUNWAY_MONTHS


def _offering_type(value: str) -> str:
    """Normalise the model's classification to one of OFFERING_TYPES."""
    v = str(value).strip().lower()
    if v in OFFERING_TYPES:
        return v
    # Word boundaries so "apparel" isn't read as an "app".
    if re.search(r"\b(saas|software|apps?|digital|platform)\b", v):
        return "software"
    if "serv" in v:
        return "service"
    return "physical"


class IntakeAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model_name = model
        register_role("Intake Analyst", "intake", model)
        llm = LLM(model=model, max_tokens=AGENT_MAX_TOKENS["intake"])
        self._agent = Agent(
            role="Intake Analyst",
            goal="Turn a founder's raw pitch or business description into structured data",
            backstory="You listen to founders describe their business in their own words and "
            "extract a clean structured record, without inventing details they didn't give you.",
            llm=llm,
            verbose=False,
        )

    @cached("intake", BusinessInput)
    @retry_on_rate_limit()
    def process(self, raw_input: str) -> BusinessInput:
        task = Task(
            description=f"{_INSTRUCTION}\n\nFounder's input:\n\n{raw_input}\n\nExtract the structured record.",
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=IntakeOutputSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed: IntakeOutputSchema = task.output.pydantic

        existing_metrics = {}
        if parsed.mode == "existing_business":
            existing_metrics = {
                "revenue": parsed.existing_revenue,
                "pat": parsed.existing_pat,
                "ebitda": parsed.existing_ebitda,
                "debt": parsed.existing_debt,
            }

        return BusinessInput(
            mode=parsed.mode,
            business_summary=parsed.business_summary,
            industry=parsed.industry,
            product_or_service=parsed.product_or_service,
            target_region=parsed.target_region,
            existing_metrics=existing_metrics,
            raw_input=raw_input,
            offering_type=_offering_type(parsed.offering_type),
        )
