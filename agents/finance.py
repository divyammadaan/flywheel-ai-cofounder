"""Finance agent — the money math behind every plan.

  launch    how much of the founder's capital can go into the launch once a
            reserve for running costs is held back, and what break-even takes
            (units a month whose margin covers fixed costs).
  existing  runway at the current profit or loss, debt against a year of
            revenue, and whether next period's budget fits the cash in the bank.

Then it splits the spendable budget across the planning areas based on
Strategy's priorities, with a hard per-area cap.

All of that is plain Python (agents/_cash.py, compute_capped_allocation),
deliberately NOT delegated to the LLM -- a guardrail must hold even if the
model's reasoning is wrong. A Google ADK LlmAgent only explains the result and
names the biggest cash risk in plain words.

Backed by Groq (via LiteLlm), not Gemini directly -- see strategy.py for
why (Gemini's free-tier 20 req/day cap).
"""

import asyncio
from dataclasses import dataclass, field

from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents._cash import launch_cash_plan, operating_cash_position
from agents._models import AGENT_MODELS
from agents._money import fmt_money
from agents._retry import retry_on_rate_limit
from agents.analytics import PeriodMetrics

APP_NAME = "flywheel"
USER_ID = "flywheel_run"
DEFAULT_MODEL = AGENT_MODELS["finance"]

# Guardrail: no single area may receive more than this fraction of budget.
MAX_SHARE_PER_AGENT = 0.6

_INSTRUCTION = """You are the Finance agent for Flywheel, an AI co-founder. You're given a cash
check computed in code (reserve, runway, break-even, debt -- whichever apply), the budget the
founder can spend, Strategy's requested priority split, and the allocation after a hard
per-area spend cap was applied in code.

Write 2-3 sentences: explain the split, say if the cap trimmed anything, and state the most
important cash risk from the cash check in plain words (e.g. "you need 223 subscribers a
month to cover fixed costs"). Do not recompute or invent numbers -- use the ones you're
given, in the same currency."""


def compute_capped_allocation(total_budget: float, priorities: dict) -> dict:
    """Pure, deterministic guardrail logic: normalize priorities, cap each
    area's share at MAX_SHARE_PER_AGENT. No LLM involved, so this is unit
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
    currency: str = "INR"
    # The cash check from agents/_cash.py this allocation was based on.
    health: dict = field(default_factory=dict)

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
            if amount > self.total_budget * MAX_SHARE_PER_AGENT + 1e-6:
                raise ValueError(f"{name} allocation {amount} exceeds guardrail cap")


class FinanceAgent:
    """Cash math and guardrail-enforced allocation (plain Python) plus an ADK
    LlmAgent that explains them."""

    def __init__(self, currency: str, model: str = DEFAULT_MODEL, session_id: str = "finance_session"):
        self.currency = currency
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

    def plan_launch(
        self,
        cycle: int,
        priorities: dict,
        capital: float,
        price: float,
        monthly_fixed_costs: float | None,
        unit_cost: float | None,
        runway_months: int,
    ) -> BudgetAllocation:
        health = launch_cash_plan(capital, price, monthly_fixed_costs, unit_cost, runway_months)
        return self.allocate(cycle, priorities, health["launch_budget"], health)

    def plan_operating(self, cycle: int, priorities: dict, metrics: PeriodMetrics, budget: float) -> BudgetAllocation:
        health = operating_cash_position(
            metrics.revenue, metrics.net_profit, metrics.total_debt, budget, metrics.period_months, metrics.cash_in_bank
        )
        return self.allocate(cycle, priorities, budget, health)

    async def _allocate_async(self, cycle: int, priorities: dict, total_budget: float, health: dict) -> BudgetAllocation:
        await self._ensure_session()
        amounts = compute_capped_allocation(total_budget, priorities)

        message = (
            f"Plan period {cycle}. Cash check (computed in code, {self.currency}): {health}\n"
            f"Budget to spend: {fmt_money(total_budget, self.currency)}. "
            f"Strategy requested priorities: {priorities}. "
            f"After the guardrail cap ({MAX_SHARE_PER_AGENT:.0%} max per area), "
            f"allocated in {self.currency}: {amounts}."
        )
        content = types.Content(role="user", parts=[types.Part(text=message)])

        rationale = ""
        async for event in self._runner.run_async(user_id=USER_ID, session_id=self._session_id, new_message=content):
            if event.is_final_response() and event.content and event.content.parts:
                rationale = event.content.parts[0].text.strip()

        return BudgetAllocation(
            cycle=cycle,
            total_budget=total_budget,
            rationale=rationale,
            currency=self.currency,
            health=health,
            **amounts,
        )

    @retry_on_rate_limit()
    def allocate(self, cycle: int, priorities: dict, total_budget: float, health: dict) -> BudgetAllocation:
        return asyncio.run(self._allocate_async(cycle, priorities, total_budget, health))
