"""Strategy agent — sets the plan every other planning agent executes:
positioning, target customer, a real price, and how the budget should be
split.

Two modes (see agents/_brief.py):
  launch    the business hasn't launched -- plan from the market research and
            the Founder Advisor's verdict. There are no results to react to.
  existing  an operating business -- plan from the founder's real reported
            numbers and the Analytics summary of them.

Every plan is checked in code before anyone uses it (agents/_guardrails.py,
applied in orchestration/cycle.py): wrong business, wrong units, a price far
from what customers pay, or demeaning wording sends it back once for a fix.

Built on Google ADK: an LlmAgent with output_schema, so the reply is parsed
straight into StrategyOutput.

Backed by Groq (via LiteLlm), not Gemini directly: Gemini's free Developer
API tier caps gemini-3.6-flash at 20 requests/day per project. Pass
model="gemini-3.6-flash" to StrategyAgent to use Gemini directly instead.
"""

import asyncio
from dataclasses import dataclass

from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from agents._brief import LAUNCH
from agents._models import GROQ_MODEL_ADK_JSON
from agents._retry import retry_on_rate_limit

# Not GROQ_MODEL: this is the one agent using ADK's output_schema, which
# needs a model that returns bare JSON with no preamble. See _models.py.
DEFAULT_MODEL = GROQ_MODEL_ADK_JSON

APP_NAME = "flywheel"
USER_ID = "flywheel_run"

_INSTRUCTION = """You are the Strategy agent for Flywheel, an AI co-founder. You set the plan
that the Finance, Marketing, Sales, Product and CRM agents will carry out.

The message tells you which mode you are in:
- PRE-LAUNCH: the business has not launched. There are no customers, sales or revenue yet.
  Build the launch plan from the market research and the Founder Advisor's verdict. Never
  describe results as if they had happened.
- OPERATING BUSINESS: you are given the founder's real reported numbers and the Analytics
  summary of them. Plan the next period in direct response to those numbers.

Set:
- positioning: one sentence about exactly what THIS business sells.
- target_customer: who buys and where -- age band, occupation, city localities.
- price and price_unit: a real price in the currency you are told, and what it buys
  (e.g. price 799, price_unit "per month, 1kg subscription"). Never a 0..1 weight.
- priority_marketing, priority_product, priority_sales, priority_crm: weights that sum to
  1.0, for how the budget should be split.
- rationale: 2-3 sentences tied to the research or to the reported numbers.

Rules:
- Stay on the business you are given. Don't turn it into a different product.
- Use the plan currency. For a business in India, use metric units (g, kg, ml).
- If the founder's answers or the order history show what customers will pay, keep the
  price near that unless you say why.
- Describe customers by what they want and can afford. Never characterise neighbourhoods
  or communities, and never use demeaning terms about any group of people.

Be specific to this business and region. BE CONCISE."""


class StrategyOutput(BaseModel):
    positioning: str = Field(description="One-sentence market positioning for what this business sells")
    target_customer: str = Field(description="Who buys and where: age band, occupation, city localities")
    # A real price plus what it buys. This used to be one float described as
    # "USD", sitting between four 0..1 priority weights, and the model copied
    # the weights: a Rs 799/month subscription came back priced at 0.55.
    price: float = Field(description="Price in the plan currency, e.g. 799 -- a real price, not a 0..1 weight")
    price_unit: str = Field(description="What that price buys, e.g. 'per month, 1kg subscription'")
    # Explicit fields rather than dict[str, float]: Gemini's Developer API (free
    # AI Studio tier) rejects open-ended dict/additionalProperties schemas for
    # structured output -- that's only supported in Vertex/Enterprise mode.
    priority_marketing: float = Field(description="Budget priority weight for marketing, 0..1")
    priority_product: float = Field(description="Budget priority weight for product, 0..1")
    priority_sales: float = Field(description="Budget priority weight for sales, 0..1")
    priority_crm: float = Field(description="Budget priority weight for crm, 0..1")
    rationale: str = Field(description="2-3 sentences tied to the research or the reported numbers")

    def priorities_dict(self) -> dict:
        return {
            "marketing": self.priority_marketing,
            "product": self.priority_product,
            "sales": self.priority_sales,
            "crm": self.priority_crm,
        }


@dataclass
class StrategyDecision:
    cycle: int
    mode: str
    currency: str
    positioning: str
    target_customer: str
    price: float
    price_unit: str
    priorities: dict
    rationale: str


class StrategyAgent:
    """Google ADK LlmAgent, with per-run session memory -- so a plan sent back
    by the checker is revised in the same conversation, not from scratch."""

    def __init__(self, model: str = DEFAULT_MODEL, session_id: str = "strategy_session"):
        resolved_model = LiteLlm(model=model) if model.startswith("groq/") else model
        self._agent = LlmAgent(
            name="strategy_agent",
            model=resolved_model,
            instruction=_INSTRUCTION,
            output_schema=StrategyOutput,
            output_key="strategy_output",
        )
        self._session_service = InMemorySessionService()
        self._runner = Runner(agent=self._agent, app_name=APP_NAME, session_service=self._session_service)
        self._session_id = session_id
        self._session_ready = False

    async def _ensure_session(self):
        if not self._session_ready:
            await self._session_service.create_session(
                app_name=APP_NAME, user_id=USER_ID, session_id=self._session_id
            )
            self._session_ready = True

    async def _decide_async(
        self, cycle: int, mode: str, currency: str, context: str, business_line: str
    ) -> StrategyDecision:
        await self._ensure_session()

        stage = "PRE-LAUNCH (not launched yet)" if mode == LAUNCH else "OPERATING BUSINESS"
        message = (
            f"Mode: {stage}. Plan period: {cycle}. Plan currency: {currency}.\n"
            f"{business_line}\n\n{context}\n\nSet the plan."
        )
        content = types.Content(role="user", parts=[types.Part(text=message)])

        final_text = None
        async for event in self._runner.run_async(user_id=USER_ID, session_id=self._session_id, new_message=content):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = event.content.parts[0].text

        if final_text is None:
            raise RuntimeError("Strategy agent produced no response")

        parsed = StrategyOutput.model_validate_json(final_text)
        return StrategyDecision(
            cycle=cycle,
            mode=mode,
            currency=currency,
            positioning=parsed.positioning,
            target_customer=parsed.target_customer,
            price=parsed.price,
            price_unit=parsed.price_unit,
            priorities=parsed.priorities_dict(),
            rationale=parsed.rationale,
        )

    @retry_on_rate_limit()
    def decide(self, cycle: int, mode: str, currency: str, context: str, business_line: str) -> StrategyDecision:
        return asyncio.run(self._decide_async(cycle, mode, currency, context, business_line))
