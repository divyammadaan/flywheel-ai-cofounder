"""A2A bridge — exposes the Marketing agent (CrewAI) over Google's
Agent2Agent protocol, so the engine can hand work across a framework
boundary as a real protocol call rather than a Python method call.

Why this seam. Everything else in Flywheel talks in-process:
`marketing.execute(...)` is just an object call inside cycle.py. That works,
but it isn't agent-to-agent communication in any meaningful sense -- the
caller has to import the callee and know its framework. A2A replaces that
with discovery (an Agent Card published at a well-known URL saying what the
agent can do) plus a transport, so an ADK-side caller can drive a CrewAI
agent without importing or knowing anything about CrewAI.

Marketing was chosen because it sits exactly on the ADK->CrewAI seam: it
consumes positioning and pricing that the ADK Strategy agent produced.

Run the server:
    .venv/Scripts/python orchestration/a2a_bridge.py
    # Agent Card: http://localhost:8600/.well-known/agent-card.json

The engine calls `request_marketing(...)`, which uses A2A when the server is
reachable and falls back to a direct in-process call otherwise -- so the
system still runs with no server up, and the protocol path is a genuine
upgrade rather than a new hard dependency.
"""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, Message, Part, Role
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, VERSION_HEADER

from agents._brief import PlanBrief
from agents.marketing import MarketingAgent, MarketingOutput

HOST = "127.0.0.1"
PORT = 8600
BASE_URL = f"http://{HOST}:{PORT}"
AGENT_CARD_PATH = "/.well-known/agent-card.json"
RPC_URL = "/a2a"

# Short: this is a liveness probe on localhost, not a real network call. If
# the server isn't up we want the fallback immediately, not after a stall.
DISCOVERY_TIMEOUT = 2.0
CALL_TIMEOUT = 180.0


# The example other agents copy from the Agent Card. Built from PlanBrief
# itself, so it can't drift from the fields the executor actually reads.
_EXAMPLE_BRIEF = PlanBrief(
    cycle=1,
    mode="launch",
    business_summary="Custom celebration cakes made to order in Pune",
    industry="D2C bakery",
    product_or_service="custom cakes",
    region="Pune, India",
    currency="INR",
    positioning="Designer cakes delivered the same day",
    target_customer="Parents aged 28-45 in Baner and Aundh",
    price=1800.0,
    price_unit="per 1kg cake",
)


def build_agent_card() -> AgentCard:
    """The manifest other agents discover. Describes capability, not
    implementation -- nothing here reveals that Marketing runs on CrewAI,
    which is the point of the protocol."""
    return AgentCard(
        name="flywheel-marketing",
        description=(
            "Plans specific ad campaigns (platform, targeting, format, timing, spend) "
            "and writes the matching ad copy and image, from a business brief and a "
            "marketing budget."
        ),
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        skills=[
            AgentSkill(
                id="plan_campaigns",
                name="Plan marketing campaigns",
                description=(
                    "Given a plan brief (business, region, currency, positioning, target "
                    "customer, price) and a marketing budget, returns 2-4 campaigns whose "
                    "budgets fit, the ad copy, and the ad image path."
                ),
                tags=["marketing", "campaigns", "copywriting", "flywheel"],
                examples=[json.dumps({"budget": 200000.0, "brief": asdict(_EXAMPLE_BRIEF)})],
                input_modes=["text/plain"],
                output_modes=["application/json"],
            )
        ],
    )


class MarketingExecutor(AgentExecutor):
    """Adapts the CrewAI MarketingAgent to A2A's executor interface."""

    def __init__(self) -> None:
        self._agent = MarketingAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        payload = json.loads(context.get_user_input())
        # to_thread, not a direct call: MarketingAgent.execute runs
        # crew.kickoff(), which is synchronous and refuses to run inside an
        # active event loop ("Agent execution was invoked synchronously from
        # within a running event loop"). The A2A server is async, so the
        # blocking work has to move off the loop thread.
        brief = PlanBrief(**payload["brief"])
        result = await asyncio.to_thread(self._agent.execute, brief, float(payload["budget"]))
        await event_queue.enqueue_event(
            Message(
                message_id=f"marketing-{brief.cycle}",
                role=Role.ROLE_AGENT,
                parts=[Part(text=json.dumps(asdict(result)))],
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # A single ad-copy generation is short and has no external side
        # effects, so there is nothing meaningful to roll back.
        raise NotImplementedError("MarketingExecutor does not support cancellation")


def create_app():
    """Starlette, deliberately, not FastAPI.

    a2a exposes its routes as plain Starlette Routes and ships
    add_a2a_routes_to_fastapi() as a convenience -- but mounting them on
    FastAPI makes it generate an OpenAPI schema over the A2A protobuf types,
    which blows up in a2a's own _proto_schema.py:

        AttributeError: 'google._upb._message.FieldDescriptor'
                        object has no attribute 'is_repeated'

    That's a version mismatch between a2a-sdk and the pinned protobuf (5.29.6,
    which is itself pinned to keep a2a-sdk and the google stack compatible --
    see docs/setup.md). Both route builders work fine on their own; only the
    FastAPI schema pass fails. Starlette doesn't introspect schemas, so it
    sidesteps the bug entirely without touching the pin.
    """
    from starlette.applications import Starlette

    card = build_agent_card()
    handler = DefaultRequestHandler(
        agent_executor=MarketingExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = [
        *create_agent_card_routes(card, card_url=AGENT_CARD_PATH),
        *create_jsonrpc_routes(handler, rpc_url=RPC_URL),
    ]
    return Starlette(routes=routes)


# ------------------------------------------------------------------ client --


def server_is_up(base_url: str = BASE_URL) -> bool:
    """Discovery: can we fetch the Agent Card? Fetching the card (rather than
    pinging a port) is the protocol's own liveness signal."""
    try:
        r = httpx.get(f"{base_url}{AGENT_CARD_PATH}", timeout=DISCOVERY_TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


def request_marketing(
    brief: PlanBrief,
    budget: float,
    base_url: str = BASE_URL,
) -> tuple[MarketingOutput, str]:
    """Ask Marketing for its campaign plan, over A2A if the server is reachable.

    Returns (result, transport) so callers can log which path was taken --
    a silent fallback would make it impossible to tell whether the protocol
    is actually being exercised in a demo.
    """
    if server_is_up(base_url):
        try:
            return _request_over_a2a(brief, budget, base_url), "a2a"
        except Exception as exc:  # noqa: BLE001 - fall back, but say why
            print(f"[a2a] call failed ({type(exc).__name__}: {exc}); falling back to direct call")

    return (
        MarketingAgent().execute(brief, budget),
        "direct",
    )


def _request_over_a2a(brief: PlanBrief, budget: float, base_url: str) -> MarketingOutput:
    # "SendMessage", not the "message/send" spelling seen in some A2A docs:
    # this SDK routes JSON-RPC by gRPC service method name (see
    # jsonrpc_dispatcher.METHOD_TO_MODEL). The other spelling returns
    # -32601 Method not found.
    request = {
        "jsonrpc": "2.0",
        "id": f"cycle-{brief.cycle}",
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": f"req-{brief.cycle}",
                "role": "ROLE_USER",
                "parts": [
                    {
                        "text": json.dumps({"budget": budget, "brief": asdict(brief)})
                    }
                ],
            }
        },
    }
    # The A2A-Version header is required. Omitting it does not default to
    # "current" -- the server reads a missing header as protocol 0.3 and
    # rejects the call with -32009 VERSION_NOT_SUPPORTED.
    r = httpx.post(
        f"{base_url}{RPC_URL}",
        json=request,
        headers={VERSION_HEADER: PROTOCOL_VERSION_CURRENT},
        timeout=CALL_TIMEOUT,
    )
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"A2A error: {body['error']}")

    text = _extract_text(body["result"])
    return MarketingOutput(**json.loads(text))


def _extract_text(result: dict) -> str:
    """Pull the text part out of an A2A result.

    The shape varies by how the agent responded: a direct reply arrives as
    {"message": {"parts": [...]}}, while a longer-running one comes back as a
    task carrying status.message and/or history. Check all of them rather
    than assuming one, since which you get depends on the executor.
    """
    candidates = [
        result.get("message"),
        result,
        result.get("status", {}).get("message"),
        *result.get("history", []),
    ]
    for candidate in candidates:
        for part in (candidate or {}).get("parts", []):
            if part.get("text"):
                return part["text"]
    raise RuntimeError(f"No text part in A2A result: {result}")


if __name__ == "__main__":
    import uvicorn

    print(f"Flywheel A2A server -- Marketing agent")
    print(f"  Agent Card: {BASE_URL}{AGENT_CARD_PATH}")
    print(f"  RPC:        {BASE_URL}{RPC_URL}")
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="warning")
