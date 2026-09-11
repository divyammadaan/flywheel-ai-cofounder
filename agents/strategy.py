"""Strategy agent — reads last cycle's Analytics summary and revises the
business plan (positioning, pricing, priorities) for the next cycle.

Built on Google ADK: an LlmAgent with ADK session state carrying the run's
conversation history so each revision is grounded in what actually
happened, not just re-derived from scratch.

Backed by Groq (via LiteLlm), not Gemini directly: Gemini's free Developer
API tier caps gemini-3.6-flash at 20 requests/day per project, which a
single multi-cycle run burns through fast. Groq's free tier via ADK's
LiteLlm wrapper avoids that ceiling; pass model="gemini-3.6-flash" to
StrategyAgent to use Gemini directly instead.
"""

import asyncio
from dataclasses import dataclass

from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

DEFAULT_MODEL = "groq/qwen/qwen3.8-27b"

APP_NAME = "flywheel"
USER_ID = "flywheel_run"

_INSTRUCTION = """You are the Strategy agent for Flywheel, a simulated startup run as a
closed loop of plan -> fund -> execute -> measure -> revise cycles.

Each cycle you set positioning, a price point, and priority weights (priority_marketing,
priority_product, priority_sales, priority_crm -- must sum to 1.0) for how the shared
budget should be split. Base your revision
on the previous cycle's Analytics summary you're given -- react to what actually happened
(revenue, conversion rate, CAC, churn, any shocks) rather than restating the same plan.
Keep pricing and positioning changes incremental cycle to cycle unless the data justifies
a sharp pivot."""


class StrategyOutput(BaseModel):
    positioning: str = Field(description="One-sentence market positioning for this cycle")
    pricing: float = Field(description="Price point in USD for this cycle")
    # Explicit fields rather than dict[str, float]: Gemini's Developer API (free
    # AI Studio tier) rejects open-ended dict/additionalProperties schemas for
    # structured output -- that's only supported in Vertex/Enterprise mode.
    priority_marketing: float = Field(description="Budget priority weight for marketing, 0..1")
    priority_product: float = Field(description="Budget priority weight for product, 0..1")
    priority_sales: float = Field(description="Budget priority weight for sales, 0..1")
    priority_crm: float = Field(description="Budget priority weight for crm, 0..1")
    rationale: str = Field(description="1-2 sentence justification tied to the prior cycle's results")

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
    positioning: str
    pricing: float
    priorities: dict
    rationale: str


class StrategyAgent:
    """Google ADK LlmAgent, with per-run session memory."""

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

    async def _decide_async(self, cycle: int, previous_analytics_summary: str | None) -> StrategyDecision:
        await self._ensure_session()

        if previous_analytics_summary is None:
            message = f"Cycle {cycle}: no prior data yet. Propose an initial launch plan."
        else:
            message = (
                f"Cycle {cycle}: previous cycle's Analytics summary -- {previous_analytics_summary}\n"
                "Revise the plan for this cycle."
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
            positioning=parsed.positioning,
            pricing=parsed.pricing,
            priorities=parsed.priorities_dict(),
            rationale=parsed.rationale,
        )

    def decide(self, cycle: int, previous_analytics_summary: str | None) -> StrategyDecision:
        return asyncio.run(self._decide_async(cycle, previous_analytics_summary))
