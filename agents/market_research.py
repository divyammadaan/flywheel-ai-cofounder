"""Market Research agent — sizes the market, surfaces competitors/risks, and
asks the founder the follow-up questions needed before Founder Advisor can
give a verdict.

Grounded in live web search (tools/web_search.py: DuckDuckGo, free, no key).
The agent cites results as [n], and the report keeps the sources so the
founder can check them. If search is unavailable, the prompt says so and the
agent labels its figures as estimates instead.

CrewAI + Groq, same pattern as Marketing/Product/Sales.
"""

from dataclasses import dataclass, field

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._cache import cached
from agents._models import AGENT_MAX_TOKENS, AGENT_MODELS
from agents._money import fmt_money
from agents._retry import retry_on_rate_limit
from agents.intake import BusinessInput
from observability.usage import register_role
from tools.web_search import describe_sources, search_business

DEFAULT_MODEL = AGENT_MODELS["market_research"]

_INSTRUCTION = """You are the Market Research agent for an AI co-founder platform. Given a
founder's business summary, industry, target region, (if applicable) existing financials,
and web search results, produce a market analysis.

Use the web search results for competitors and market size, and cite them as [n]. Anything
a result doesn't support is your own estimate -- say so. Only name competitors that appear in
the results or that you are sure exist in this region.

Also generate 2-3 clarifying questions the founder must answer before a GO/PIVOT/NO-GO
call can be made. The founder's available capital is given to you when they stated it --
don't ask for it again. Ask about what is genuinely decision-relevant and still unknown
(e.g. sourcing and unit costs, timeline, existing customers or waitlist, unique advantage)
and keep the list short.

BE CONCISE. No field longer than ~50 words, and each question one sentence. Dense and
specific beats long. (Output length is rate-limited, so verbosity directly costs the
founder waiting time.)"""


class MarketResearchSchema(BaseModel):
    market_size_estimate: str = Field(description="Market size, citing sources as [n], or clearly labelled as an estimate")
    key_competitors: str = Field(description="2-4 real competitors or competitor types in this space, citing sources as [n]")
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
    # The web results the agent was given, in [n] order.
    sources: list = field(default_factory=list)


class MarketResearchAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model_name = model
        register_role("Market Research Analyst", "market_research", model)
        llm = LLM(model=model, max_tokens=AGENT_MAX_TOKENS["market_research"])
        self._agent = Agent(
            role="Market Research Analyst",
            goal="Size the market and identify what's still unknown before a GO/NO-GO call",
            backstory="You research markets for an AI co-founder platform. You ground claims in the "
            "sources you're given, say plainly what is only an estimate, and focus on asking the "
            "right follow-up questions rather than pretending to have data you don't.",
            llm=llm,
            verbose=False,
        )

    @cached("market_research", MarketResearchReport)
    def research(self, business: BusinessInput) -> MarketResearchReport:
        # Searched outside the rate-limit retry, so a Groq retry doesn't repeat
        # ~30s of web search.
        sources = search_business(business)
        report = self._analyse(business, sources)
        report.sources = sources
        return report

    @retry_on_rate_limit()
    def _analyse(self, business: BusinessInput, sources: list[dict]) -> MarketResearchReport:
        metrics_note = f" Existing financials: {business.existing_metrics}." if business.existing_metrics else ""
        capital_note = (
            f" Founder's available capital: {fmt_money(business.starting_capital, business.currency)}."
            if business.starting_capital
            else ""
        )
        task = Task(
            description=(
                f"{_INSTRUCTION}\n\n"
                f"Business: {business.business_summary}\n"
                f"Industry: {business.industry}. Product/service: {business.product_or_service}. "
                f"Target region: {business.target_region}.{metrics_note}{capital_note}\n\n"
                f"{describe_sources(sources)}\n\n"
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
