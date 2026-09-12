"""Company Formation agent — after a GO/PIVOT verdict, walks the founder
through the legal/compliance steps to actually incorporate: entity type,
registration steps, licences, tax registrations, cost and timeline.

IMPORTANT: this is informational guidance only, NOT legal advice, and the
model has no live access to current statutes or filing fees. Every report
carries an explicit disclaimer and the flow prints it -- compliance rules
change and vary by jurisdiction, so this is a starting checklist to take to
a real professional, never a substitute for one.

CrewAI + Groq, same pattern as the other execution agents.
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._retry import retry_on_rate_limit
from agents.intake import BusinessInput

DEFAULT_MODEL = "groq/qwen/qwen3.8-27b"

DISCLAIMER = (
    "Informational only, not legal advice. Generated without live access to current "
    "statutes or fee schedules -- verify every item with a qualified professional in "
    "your jurisdiction before filing or paying anything."
)

_INSTRUCTION = """You are the Company Formation agent for an AI co-founder platform. Given a
business and its target region, lay out the practical steps to legally form the company.

Be concrete and region-appropriate: an Indian business needs different entity types (Pvt
Ltd, LLP, OPC, sole proprietorship), registrations (GST, PAN/TAN, Udyam, Shops &
Establishment) and regulators (MCA) than a US one (LLC/C-Corp/S-Corp, EIN, state
registration, sales tax permit, DBA). If the region is unspecified or ambiguous, say so
and give the most likely default rather than inventing certainty.

Recommend ONE entity type as primary and say plainly why it fits this business's size and
risk profile. Keep cost and timeline as ranges, and flag that they're estimates.

Never state a filing fee, statute, or deadline as though it were verified current fact.

Match your specificity to your actual confidence, which differs sharply by level:
- National and state/province level (company registrar, national tax ID, state tax permit):
  be specific -- name the form and the body, these are stable and you likely know them.
- City, county, district and local office level: do NOT name a specific county, district,
  ward or local office unless you are certain it is correct for this exact city. Write
  "your city/county health department" or "the local municipal authority" instead. Naming
  the wrong county reads as authoritative and sends the founder to the wrong office, which
  is worse than being vague.

If you are unsure whether a requirement applies, say it may apply and needs checking --
do not list it as definitely required."""


class FormationSchema(BaseModel):
    recommended_entity: str = Field(description="Single recommended entity type, e.g. 'Private Limited Company'")
    entity_rationale: str = Field(description="1-2 sentences on why this entity fits this business")
    registration_steps: str = Field(description="Numbered, ordered steps to register the entity")
    licenses_and_permits: str = Field(description="Licences/permits this specific business likely needs")
    tax_registrations: str = Field(description="Tax registrations required (e.g. GST, EIN, sales tax permit)")
    estimated_cost: str = Field(description="Rough cost range, clearly flagged as an estimate")
    estimated_timeline: str = Field(description="Rough timeline range, clearly flagged as an estimate")


@dataclass
class FormationPlan:
    recommended_entity: str
    entity_rationale: str
    registration_steps: str
    licenses_and_permits: str
    tax_registrations: str
    estimated_cost: str
    estimated_timeline: str
    disclaimer: str = DISCLAIMER


class CompanyFormationAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        llm = LLM(model=model)
        self._agent = Agent(
            role="Company Formation Advisor",
            goal="Give a founder a concrete, jurisdiction-appropriate incorporation checklist",
            backstory="You help founders navigate incorporation and compliance. You're "
            "precise about what you know versus what needs a professional's sign-off, and "
            "you never present an estimate as a verified legal fact.",
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def plan(self, business: BusinessInput) -> FormationPlan:
        task = Task(
            description=(
                f"Business: {business.business_summary}\n"
                f"Industry: {business.industry}. Product/service: {business.product_or_service}. "
                f"Region: {business.target_region}. Stage: {business.mode}.\n"
                "Produce the company formation plan."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=FormationSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        p: FormationSchema = task.output.pydantic

        return FormationPlan(
            recommended_entity=p.recommended_entity,
            entity_rationale=p.entity_rationale,
            registration_steps=p.registration_steps,
            licenses_and_permits=p.licenses_and_permits,
            tax_registrations=p.tax_registrations,
            estimated_cost=p.estimated_cost,
            estimated_timeline=p.estimated_timeline,
        )
