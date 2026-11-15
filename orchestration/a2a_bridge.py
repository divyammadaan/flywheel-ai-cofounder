"""A2A bridge — exposes Flywheel's execution agents (CrewAI) over Google's
Agent2Agent protocol, so another framework's agents can hand them work across a
real protocol boundary rather than a Python method call.

Four agents are published, each with its own Agent Card and JSON-RPC endpoint:

    marketing   plans ad campaigns, ad copy and an image
    sales       plans lead sources and the lead-to-customer steps
    product     plans inventory (or delivery capacity) to fit the budget
    crm         plans win-back actions and messages per customer group

All four are CrewAI agents. The caller on the other side is Google ADK:
`orchestration/adk_coordinator.py` is an ADK agent team whose members are
ADK `RemoteA2aAgent`s, one per card, so the framework boundary is ADK <-> CrewAI
and neither side imports the other's code -- they meet only at the card and the
message.

Where the server lives
    Inside the API process, mounted at `/a2a` (see api/main.py), so a deployment
    is one service. It can also run alone:

        .venv/Scripts/python orchestration/a2a_bridge.py
        # cards at http://127.0.0.1:8600/<agent>/.well-known/agent-card.json

    Callers find it from FLYWHEEL_A2A_URL, defaulting to the API's own `/a2a`.

The engine uses A2A when the cards are reachable and falls back to calling the
agents in-process otherwise, so the system still runs with no server up and the
protocol path is an upgrade rather than a new hard dependency.

`request_marketing` (a single agent, plain JSON-RPC) is kept: it is the smallest
possible A2A client and the tests use it.
"""

import asyncio
import contextvars
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Message, Part, Role
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, VERSION_HEADER

from agents._brief import PlanBrief
from agents.crm import CRMAgent
from agents.marketing import MarketingAgent, MarketingOutput
from agents.product import ProductAgent
from agents.sales import SalesAgent
from storage.runs import using_run

HOST = "127.0.0.1"
PORT = 8600  # when run on its own; inside the API the port is the API's
AGENT_CARD_PATH = "/.well-known/agent-card.json"
RPC_URL = "/a2a"

# Short: this is a liveness probe on localhost, not a real network call. If
# the server isn't up we want the fallback immediately, not after a stall.
DISCOVERY_TIMEOUT = 2.0
CALL_TIMEOUT = 600.0  # a model call can wait out a provider rate limit


def a2a_base_url() -> str:
    """Where the agents' cards and endpoints live, without a trailing slash."""
    configured = os.environ.get("FLYWHEEL_A2A_URL", "").strip().rstrip("/")
    return configured or f"http://127.0.0.1:{os.environ.get('PORT') or 8000}/a2a"


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


@dataclass(frozen=True)
class AgentSpec:
    agent_class: type
    skill_id: str
    skill_name: str
    description: str
    skill_description: str
    tags: tuple


# One place that says what is published. The card, the executor and the
# coordinator all read from here.
SPECS: dict[str, AgentSpec] = {
    "marketing": AgentSpec(
        MarketingAgent,
        "plan_campaigns",
        "Plan marketing campaigns",
        "Plans specific ad campaigns (platform, targeting, format, timing, spend) and writes the "
        "matching ad copy and image, from a business brief and a marketing budget.",
        "Given a plan brief (business, region, currency, positioning, target customer, price) and a "
        "marketing budget, returns 2-4 campaigns whose budgets fit, the ad copy, and the ad image path.",
        ("marketing", "campaigns", "copywriting", "flywheel"),
    ),
    "sales": AgentSpec(
        SalesAgent,
        "plan_lead_sources",
        "Plan lead sources",
        "Says exactly where leads will come from and how, with a weekly cadence and a spend per source.",
        "Given a plan brief and a sales budget, returns 2-4 lead sources whose budgets fit and the "
        "ordered steps that turn a lead into a paying customer.",
        ("sales", "leads", "flywheel"),
    ),
    "product": AgentSpec(
        ProductAgent,
        "plan_product",
        "Plan inventory or capacity",
        "Plans the stock to buy (or the delivery capacity to build) for a launch or the next period, "
        "priced in code so the lines add up to the budget.",
        "Given a plan brief and a product budget, returns priced line items, a sourcing plan and a "
        "replenishment policy.",
        ("product", "inventory", "flywheel"),
    ),
    "crm": AgentSpec(
        CRMAgent,
        "plan_retention",
        "Plan customer retention",
        "Plans win-back actions, spends and ready-to-send messages for each customer group, for an "
        "operating business with an order history.",
        "Given a plan brief, a CRM budget and customer segments (and optionally last period's), returns "
        "an action and spend per group and personalised messages.",
        ("crm", "retention", "flywheel"),
    ),
}
AGENT_NAMES = tuple(SPECS)


def build_agent_card(name: str = "marketing", base_url: str | None = None) -> AgentCard:
    """The manifest other agents discover. Describes capability, not
    implementation -- nothing here reveals that the agent runs on CrewAI,
    which is the point of the protocol."""
    spec = SPECS[name]
    base = (base_url or a2a_base_url()).rstrip("/")
    return AgentCard(
        name=f"flywheel-{name}",
        description=spec.description,
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        # Where to send requests. A client (ADK's RemoteA2aAgent included)
        # refuses a card that does not say.
        supported_interfaces=[
            AgentInterface(url=f"{base}/{name}{RPC_URL}", protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        skills=[
            AgentSkill(
                id=spec.skill_id,
                name=spec.skill_name,
                description=spec.skill_description,
                tags=list(spec.tags),
                examples=[json.dumps({"budget": 200000.0, "brief": asdict(_EXAMPLE_BRIEF)})],
                input_modes=["text/plain"],
                output_modes=["application/json"],
            )
        ],
    )


class ExecutionExecutor(AgentExecutor):
    """Adapts one CrewAI agent to A2A's executor interface.

    The request is JSON text. It may be addressed to this agent alone
    ({"budget", "brief", ...}) or carry every team member's slice keyed by agent
    name ({"marketing": {...}, "sales": {...}}), which is what the ADK
    coordinator sends: one message, each agent reads its own part.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        payload = json.loads(context.get_user_input())
        mine = payload.get(self.name, payload)
        brief = PlanBrief(**mine["brief"])
        budget = float(mine["budget"])
        run_id = payload.get("run_id") or mine.get("run_id")

        def work():
            # A fresh agent per request: its model tags carry the run in progress.
            agent = SPECS[self.name].agent_class()
            if self.name == "crm":
                return agent.execute(brief, budget, mine["segments"], mine.get("previous"))
            return agent.execute(brief, budget)

        def in_run():
            # The run is bound here, on the worker thread: the server's own
            # request context knows nothing about which plan this belongs to.
            if run_id:
                with using_run(int(run_id)):
                    return work()
            return work()

        # to_thread, not a direct call: crew.kickoff() is synchronous and refuses to
        # run inside an active event loop ("Agent execution was invoked
        # synchronously from within a running event loop"), and the A2A server is async.
        result = await asyncio.to_thread(contextvars.copy_context().run, in_run)
        await event_queue.enqueue_event(
            Message(
                message_id=f"{self.name}-{brief.cycle}",
                role=Role.ROLE_AGENT,
                parts=[Part(text=json.dumps(asdict(result)))],
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # A single generation is short and has no external side effects, so
        # there is nothing meaningful to roll back.
        raise NotImplementedError("execution agents do not support cancellation")


# Kept under its old name for anything that imported it.
class MarketingExecutor(ExecutionExecutor):
    def __init__(self) -> None:
        super().__init__("marketing")


def create_app(base_url: str | None = None):
    """Starlette, deliberately, not FastAPI, with one mounted sub-app per agent.

    a2a exposes its routes as plain Starlette Routes and ships
    add_a2a_routes_to_fastapi() as a convenience -- but adding them to FastAPI's
    own route table makes it generate an OpenAPI schema over the A2A protobuf
    types, which blows up in a2a's own _proto_schema.py:

        AttributeError: 'google._upb._message.FieldDescriptor'
                        object has no attribute 'is_repeated'

    That's a version mismatch between a2a-sdk and the pinned protobuf. Both route
    builders work fine on their own; only the FastAPI schema pass fails. A
    Starlette app, mounted into FastAPI as a whole, is not part of FastAPI's
    schema, so it sidesteps the bug without touching the pin.
    """
    from starlette.applications import Starlette
    from starlette.routing import Mount

    mounts = []
    for name in AGENT_NAMES:
        card = build_agent_card(name, base_url)
        handler = DefaultRequestHandler(
            agent_executor=ExecutionExecutor(name), task_store=InMemoryTaskStore(), agent_card=card
        )
        sub = Starlette(
            routes=[
                *create_agent_card_routes(card, card_url=AGENT_CARD_PATH),
                *create_jsonrpc_routes(handler, rpc_url=RPC_URL),
            ]
        )
        mounts.append(Mount(f"/{name}", app=sub))
    return Starlette(routes=mounts)


# ------------------------------------------------------------------ client --


def _default_agent_url() -> str:
    return f"{a2a_base_url()}/marketing"


def server_is_up(base_url: str | None = None) -> bool:
    """Discovery: can we fetch the Agent Card? Fetching the card (rather than
    pinging a port) is the protocol's own liveness signal."""
    try:
        r = httpx.get(f"{base_url or _default_agent_url()}{AGENT_CARD_PATH}", timeout=DISCOVERY_TIMEOUT, headers=_auth_headers())
        return r.status_code == 200
    except Exception:
        return False


def team_is_up(base_url: str | None = None) -> bool:
    """Whether every execution agent's card can be fetched."""
    base = (base_url or a2a_base_url()).rstrip("/")
    return all(server_is_up(f"{base}/{name}") for name in AGENT_NAMES)


def _auth_headers() -> dict:
    """The deployment's access code, which also guards the A2A endpoints."""
    code = os.environ.get("FLYWHEEL_ACCESS_CODE", "").strip()
    return {"X-Access-Code": code} if code else {}


def request_marketing(
    brief: PlanBrief,
    budget: float,
    base_url: str | None = None,
) -> tuple[MarketingOutput, str]:
    """Ask Marketing for its campaign plan, over A2A if the server is reachable.

    Returns (result, transport) so callers can log which path was taken --
    a silent fallback would make it impossible to tell whether the protocol
    is actually being exercised in a demo.
    """
    base = base_url or _default_agent_url()
    if server_is_up(base):
        try:
            return _request_over_a2a(brief, budget, base), "a2a"
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
        headers={VERSION_HEADER: PROTOCOL_VERSION_CURRENT, **_auth_headers()},
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

    standalone = f"http://{HOST}:{PORT}"
    os.environ.setdefault("FLYWHEEL_A2A_URL", standalone)
    print("Flywheel A2A server -- agents: " + ", ".join(AGENT_NAMES))
    for agent in AGENT_NAMES:
        print(f"  {agent:<10} card: {standalone}/{agent}{AGENT_CARD_PATH}")
    print("Point the API at it with FLYWHEEL_A2A_URL=" + standalone)
    uvicorn.run(create_app(standalone), host=HOST, port=PORT, log_level="warning")
