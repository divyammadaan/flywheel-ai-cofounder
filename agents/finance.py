"""Finance agent — allocates a fixed shared budget across the execution
agents based on Strategy's priorities, enforcing hard spend caps (guardrail).

The spend caps are enforced in plain Python, deliberately NOT delegated to
the LLM -- a guardrail must hold even if the model's reasoning is wrong. A
Google ADK LlmAgent only narrates the resulting allocation; it never
computes the numbers.

Backed by Groq (via LiteLlm), not Gemini directly -- see strategy.py for
why (Gemini's free-tier 20 req/day cap).
"""

import asyncio
from dataclasses import dataclass

from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents._models import AGENT_MODELS
from agents._retry import retry_on_rate_limit

APP_NAME = "flywheel"
USER_ID = "flywheel_run"
DEFAULT_MODEL = AGENT_MODELS["finance"]

# Guardrail: no single agent may receive more than this fraction of budget.
MAX_SHARE_PER_AGENT = 0.6

_INSTRUCTION = """You are the Finance agent for Flywheel, a simulated startup. Each cycle
you're told the fixed total budget, Strategy's requested priority split across marketing/
product/sales/crm, and the actual allocation after a hard per-agent spend-cap guardrail
was already applied in code. Write 1-2 sentences explaining the allocation and noting if
the guardrail capped anything Strategy asked for. Do not recompute numbers -- just explain
the ones you're given."""


def compute_capped_allocation(total_budget: float, priorities: dict) -> dict:
    """Pure, deterministic guardrail logic: normalize priorities, cap each
    agent's share at MAX_SHARE_PER_AGENT. No LLM involved, so this is unit
    tested directly and always holds regardless of what any agent proposes.
    """
    total = sum(priorities.values()) or 1.0
    normalized = {k: v / total for k, v in priorities.items()}

    def capped(share: float) -> float:
        return min(share, MAX_SHARE_PER_AGENT) * total_budget

    return {
        "marketing": round(capped(normalized.get("marketing", 0)), 2),
        "product": round(capped(normalized.get("product", 0)), 2),
        "sales": round(capped(normalized.get("sales", 0)), 2),
        "crm": round(capped(normalized.get("crm", 0)), 2),
    }


@dataclass
class BudgetAllocation:
    cycle: int
    total_budget: float
    marketing: float
    product: float
    sales: float
    crm: float
    rationale: str = ""

    def __post_init__(self):
        allocated = self.marketing + self.product + self.sales + self.crm
        if allocated > self.total_budget + 1e-6:
            raise ValueError(f"Allocation {allocated} exceeds total budget {self.total_budget}")
        for name, amount in (
            ("marketing", self.marketing),
            ("product", self.product),
            ("sales", self.sales),
            ("crm", self.crm),
        ):
            if amount > self.total_budget * MAX_SHARE_PER_AGENT:
                raise ValueError(f"{name} allocation {amount} exceeds guardrail cap")


class FinanceAgent:
    """Deterministic guardrail-enforced allocation (plain Python) plus an
    ADK LlmAgent that narrates the decision, with session memory across
    cycles."""

    def __init__(
        self,
        total_budget_per_cycle: float,
        model: str = DEFAULT_MODEL,
        session_id: str = "finance_session",
    ):
        self.total_budget_per_cycle = total_budget_per_cycle
        resolved_model = LiteLlm(model=model) if model.startswith("groq/") else model
        self._agent = LlmAgent(name="finance_agent", model=resolved_model, instruction=_INSTRUCTION)
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

    async def _allocate_async(self, cycle: int, priorities: dict) -> BudgetAllocation:
        await self._ensure_session()
        amounts = compute_capped_allocation(self.total_budget_per_cycle, priorities)

        message = (
            f"Cycle {cycle}: total budget ${self.total_budget_per_cycle:.2f}. "
            f"Strategy requested priorities: {priorities}. "
            f"After the guardrail cap ({MAX_SHARE_PER_AGENT:.0%} max per agent), allocated: {amounts}."
        )
        content = types.Content(role="user", parts=[types.Part(text=message)])

        rationale = ""
        async for event in self._runner.run_async(user_id=USER_ID, session_id=self._session_id, new_message=content):
            if event.is_final_response() and event.content and event.content.parts:
                rationale = event.content.parts[0].text.strip()

        return BudgetAllocation(
            cycle=cycle,
            total_budget=self.total_budget_per_cycle,
            rationale=rationale,
            **amounts,
        )

    @retry_on_rate_limit()
    def allocate(self, cycle: int, priorities: dict) -> BudgetAllocation:
        return asyncio.run(self._allocate_async(cycle, priorities))
