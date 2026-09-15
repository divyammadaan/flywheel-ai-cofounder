"""Founder Advisor agent — the decision gate. Given the business, market
research, and the founder's answers to the clarifying questions, gives a
GO / PIVOT / NO-GO verdict and, if GO or PIVOT, a seed plan that the launch
plan's Strategy agent starts from.

CrewAI + Groq, same pattern as Marketing/Product/Sales.
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._models import AGENT_MODELS
from agents._money import fmt_money
from agents._retry import retry_on_rate_limit
from agents.intake import BusinessInput
from agents.market_research import MarketResearchReport

DEFAULT_MODEL = AGENT_MODELS["founder_advisor"]

_INSTRUCTION = """You are the Founder Advisor for an AI co-founder platform -- the final gate
before a launch plan is built. Given the business summary, the founder's capital, market
research, and the founder's own answers to the clarifying questions, give a clear verdict:
- GO: the idea is viable enough to start executing now.
- PIVOT: viable in the space, but not as currently framed -- say what should change.
- NO_GO: not viable given what you know (e.g., the capital is unrealistic for the space, or
  the market/competitive picture is too hostile).

If GO (or PIVOT -- provide the seed plan for the PIVOTED direction), also produce a seed
plan: positioning, an initial price in the founder's currency together with what it buys
(e.g. 799, "per month, 1kg subscription"), and initial budget priority weights across
marketing/product/sales/crm (must sum to 1.0). This seed plan feeds directly into the launch
plan, so ground it in the founder's actual capital and the market research, not generic
advice.

BE CONCISE. Rationale is at most ~70 words and positioning is one sentence. Say the hard
thing plainly rather than cushioning it. (Output length is rate-limited, so verbosity
directly costs the founder waiting time.)"""


class AdvisorOutputSchema(BaseModel):
    verdict: str = Field(description="One of: GO, PIVOT, NO_GO")
    rationale: str = Field(description="2-4 sentence justification citing the market research and founder's answers")
    seed_positioning: str = Field(description="One-sentence positioning for the launch (empty if NO_GO)")
    seed_price: float = Field(
        default=0.0,
        description="Initial price in the founder's currency, e.g. 799 -- a real price, not a 0..1 weight (0 if NO_GO)",
    )
    seed_price_unit: str = Field(
        default="", description="What that price buys, e.g. 'per month, 1kg subscription' (empty if NO_GO)"
    )
    seed_priority_marketing: float = Field(default=0.0)
    seed_priority_product: float = Field(default=0.0)
    seed_priority_sales: float = Field(default=0.0)
    seed_priority_crm: float = Field(default=0.0)


@dataclass
class AdvisorDecision:
    verdict: str
    rationale: str
    seed_positioning: str
    seed_price: float
    seed_price_unit: str
    seed_priorities: dict


class FounderAdvisorAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        llm = LLM(model=model)
        self._agent = Agent(
            role="Founder Advisor",
            goal="Give a clear-eyed GO/PIVOT/NO-GO verdict grounded in real constraints",
            backstory="You've advised many first-time founders. You don't sugarcoat a bad "
            "idea, and you don't wave through a plan that doesn't match the founder's actual "
            "budget. Your job is to protect their time and money, not to be encouraging.",
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def decide(
        self, business: BusinessInput, research: MarketResearchReport, qa_answers: dict[str, str]
    ) -> AdvisorDecision:
        qa_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in qa_answers.items())
        task = Task(
            description=(
                f"Business: {business.business_summary} (industry: {business.industry}, "
                f"region: {business.target_region})\n"
                f"Founder's capital: {fmt_money(business.starting_capital, business.currency)} "
                f"(currency {business.currency}).\n\n"
                f"Market research:\n"
                f"- Size: {research.market_size_estimate}\n"
                f"- Competitors: {research.key_competitors}\n"
                f"- Opportunities: {research.opportunities}\n"
                f"- Risks: {research.risks}\n\n"
                f"Founder's answers to clarifying questions:\n{qa_text}\n\n"
                "Give your verdict and, if GO or PIVOT, the seed plan."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=AdvisorOutputSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed: AdvisorOutputSchema = task.output.pydantic

        return AdvisorDecision(
            verdict=parsed.verdict,
            rationale=parsed.rationale,
            seed_positioning=parsed.seed_positioning,
            seed_price=parsed.seed_price,
            seed_price_unit=parsed.seed_price_unit,
            seed_priorities={
                "marketing": parsed.seed_priority_marketing,
                "product": parsed.seed_priority_product,
                "sales": parsed.seed_priority_sales,
                "crm": parsed.seed_priority_crm,
            },
        )
