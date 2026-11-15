"""A retried ADK call must not grow: each failed attempt starts a clean session."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from agents.analytics import AnalyticsAgent
from agents.strategy import StrategyAgent

STRATEGY_REPLY = json.dumps(
    {
        "positioning": "x", "target_customer": "y", "price": 1.0, "price_unit": "u",
        "priority_marketing": 0.3, "priority_product": 0.3, "priority_sales": 0.3, "priority_crm": 0.1,
        "rationale": ["r"],
    }
)


def _flaky_model(failures: int, reply: str, seen: list):
    """A stand-in model that fails `failures` times (like a provider rate limit), then answers."""

    class Flaky(BaseLlm):
        model: str = "flaky"

        async def generate_content_async(self, llm_request, stream=False):
            seen.append(sum(1 for c in llm_request.contents if c.role == "user"))
            if len(seen) <= failures:
                raise RuntimeError("rate_limit_exceeded")
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=reply)]))

    return Flaky()


def test_strategy_retries_send_the_same_size_request_every_time():
    seen: list[int] = []
    agent = StrategyAgent()
    agent._agent.model = _flaky_model(3, STRATEGY_REPLY, seen)
    agent._agent.before_model_callback = None

    attempts = 0
    result = None
    while result is None and attempts < 6:
        attempts += 1
        try:
            result = asyncio.run(agent._decide_async(1, "launch", "INR", "context", "line"))
        except RuntimeError:
            continue  # what retry_on_rate_limit does: call again

    assert result is not None and result.price == 1.0
    # One user message in every request: 1, 1, 1, 1 -- not 1, 2, 3, 4.
    assert seen == [1, 1, 1, 1]


def test_a_deliberate_revision_after_a_good_reply_keeps_its_session():
    """The guardrail's second attempt must still see the first plan."""
    seen: list[int] = []
    agent = StrategyAgent()
    agent._agent.model = _flaky_model(0, STRATEGY_REPLY, seen)
    agent._agent.before_model_callback = None

    asyncio.run(agent._decide_async(1, "launch", "INR", "context", "line"))
    asyncio.run(agent._decide_async(1, "launch", "INR", "context + feedback", "line"))
    assert seen == [1, 2]


def test_analytics_retries_do_not_grow_either():
    from agents.analytics import PeriodMetrics

    reply = json.dumps({"headline": "h", "points": ["p"], "summary": "s"})
    seen: list[int] = []
    agent = AnalyticsAgent()
    agent._agent.model = _flaky_model(2, reply, seen)
    agent._agent.before_model_callback = None
    metrics = PeriodMetrics(period_label="FY", revenue=100.0, net_profit=10.0, total_debt=5.0)

    for _ in range(4):
        try:
            asyncio.run(agent._summarize_async(1, metrics, "INR", "biz", [], None))
            break
        except RuntimeError:
            continue
    assert seen == [1, 1, 1]
