"""Market Research agent — sizes the market, surfaces competitors/risks, and
asks the founder the follow-up questions needed before Founder Advisor can
give a verdict (e.g. "how much can you invest?").

NOTE: reasons from the LLM's own general knowledge, not live web search --
no search API is wired in yet. Every report says so explicitly so it's
never mistaken for verified current data. Wiring a real search tool (e.g.
via MCP) is a natural fast-follow, not done here to avoid blocking on
another API key signup mid-build.

CrewAI + Groq, same pattern as Marketing/Product/Sales.
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._models import AGENT_MODELS
from agents._money import fmt_money
from agents._retry import retry_on_rate_limit
from agents.intake import BusinessInput

DEFAULT_MODEL = AGENT_MODELS["market_research"]

_INSTRUCTION = """You are the Market Research agent for an AI co-founder platform. Given a
founder's business summary, industry, target region, and (if applicable) existing
financials, produce a market analysis.

IMPORTANT: You do not have live web/search access. Base your analysis on general knowledge
and reasoning, and be explicit that figures are estimates, not verified current data.

Also generate 2-3 clarifying questions the founder must answer before a GO/PIVOT/NO-GO
call can be made. The founder's available capital is given to you when they stated it --
don't ask for it again. Ask about what is genuinely decision-relevant and still unknown
(e.g. sourcing and unit costs, timeline, existing customers or waitlist, unique advantage)
and keep the list short.

BE CONCISE. No field longer than ~50 words, and each question one sentence. Dense and
specific beats long. (Output length is rate-limited, so verbosity directly costs the
founder waiting time.)"""


class MarketResearchSchema(BaseModel):
    market_size_estimate: str = Field(description="Rough TAM/market size estimate with the caveat that it's an estimate")
    key_competitors: str = Field(description="2-4 known competitors or competitor types in this space")
    opportunities: str = Field(description="1-2 sentence opportunity assessment")
    risks: str = Field(description="1-2 sentence risk assessment")
    clarifying_question_1: str = Field(description="First question to ask the founder")
    clarifying_question_2: str = Field(default="", description="Second question, empty string if not needed")
    clarifying_question_3: str = Field(default="", description="Third question, empty string if not needed")


@dataclass
class MarketResearchReport:
    market_size_estimate: str
    key_competitors: str
    opportunities: str
    risks: str
    clarifying_questions: list[str]


class MarketResearchAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        llm = LLM(model=model)
        self._agent = Agent(
            role="Market Research Analyst",
            goal="Size the market and identify what's still unknown before a GO/NO-GO call",
            backstory="You research markets for an AI co-founder platform. You're upfront "
            "about the limits of your knowledge (no live web access) and focus on asking the "
            "right follow-up questions rather than pretending to have data you don't.",
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def research(self, business: BusinessInput) -> MarketResearchReport:
        metrics_note = f" Existing financials: {business.existing_metrics}." if business.existing_metrics else ""
        capital_note = (
            f" Founder's available capital: {fmt_money(business.starting_capital, business.currency)}."
            if business.starting_capital
            else ""
        )
        task = Task(
            description=(
                f"Business: {business.business_summary}\n"
                f"Industry: {business.industry}. Product/service: {business.product_or_service}. "
                f"Target region: {business.target_region}.{metrics_note}{capital_note}\n"
                "Produce the market analysis and clarifying questions."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=MarketResearchSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed: MarketResearchSchema = task.output.pydantic

        questions = [
            q for q in (parsed.clarifying_question_1, parsed.clarifying_question_2, parsed.clarifying_question_3) if q
        ]

        return MarketResearchReport(
            market_size_estimate=parsed.market_size_estimate,
            key_competitors=parsed.key_competitors,
            opportunities=parsed.opportunities,
            risks=parsed.risks,
            clarifying_questions=questions,
        )
