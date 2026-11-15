"""The ADK coordinator: Google ADK agents that hand work to CrewAI agents over A2A.

The execution stage of a plan -- Marketing, Sales, Product and (for an operating
business) CRM -- is CrewAI agents. This module is the ADK side of that boundary:

    ADK ParallelAgent  "execution_team"
        RemoteA2aAgent "marketing_remote"  --A2A-->  CrewAI Marketing agent
        RemoteA2aAgent "sales_remote"      --A2A-->  CrewAI Sales agent
        RemoteA2aAgent "product_remote"    --A2A-->  CrewAI Product agent
        RemoteA2aAgent "crm_remote"        --A2A-->  CrewAI CRM agent

Each remote agent is built from the Agent Card the server publishes, so this
code never imports a CrewAI agent: it knows a card URL and a JSON message shape.
The ParallelAgent runs the members concurrently (the same fan-out the in-process
path does with a thread pool), and an ADK session carries the shared context --
the plan brief and the budgets -- as session state, alongside the run id.

`run_execution_team` raises if anything is wrong (a card is unreachable, a member
returns nothing); the caller falls back to the in-process path, so A2A is an
upgrade, never a new way for a plan to fail.
"""

import asyncio
import json
import os
import uuid

import httpx
from a2a.types import AgentCard
from google.adk.agents import ParallelAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from google.protobuf.json_format import ParseDict

from agents.crm import CRMOutput
from agents.marketing import MarketingOutput
from agents.product import ProductOutput
from agents.sales import SalesOutput
from observability.callbacks import log
from orchestration.a2a_bridge import (
    AGENT_CARD_PATH,
    CALL_TIMEOUT,
    RPC_URL,
    SPECS,
    a2a_base_url,
    team_is_up,
    _auth_headers,
)

APP_NAME = "flywheel_execution_team"
USER_ID = "flywheel"

OUTPUT_CLASSES = {
    "marketing": MarketingOutput,
    "sales": SalesOutput,
    "product": ProductOutput,
    "crm": CRMOutput,
}


def a2a_enabled(base_url: str | None = None) -> bool:
    """Whether to use the A2A team: not switched off, and every card reachable.

    FLYWHEEL_A2A=off forces the in-process path; anything else means "use A2A
    when the agents are actually being served".
    """
    if os.environ.get("FLYWHEEL_A2A", "auto").strip().lower() in {"0", "off", "false", "no"}:
        return False
    return team_is_up(base_url)


def _json_default(value):
    # Segment tables come from pandas: numpy numbers are not JSON, but they know how to become Python ones.
    return value.item() if hasattr(value, "item") else str(value)


async def _load_card(client: httpx.AsyncClient, base: str, name: str) -> AgentCard:
    """Discover an agent: fetch the card it publishes.

    The card's interface URL is rewritten to the address it was fetched from. A
    card built for one address must still work when the server is reached by
    another (a different port or host), and the address we used to discover it
    is by definition one that works.
    """
    response = await client.get(f"{base}/{name}{AGENT_CARD_PATH}")
    response.raise_for_status()
    card = ParseDict(response.json(), AgentCard())
    for interface in card.supported_interfaces:
        interface.url = f"{base}/{name}{RPC_URL}"
    return card


def _remote(name: str, card: AgentCard, client: httpx.AsyncClient) -> RemoteA2aAgent:
    async def before(callback_context):
        log("a2a", name, "request sent to the remote agent over A2A")
        return None

    async def after(callback_context):
        log("a2a", name, "reply received over A2A")
        return None

    return RemoteA2aAgent(
        name=f"{name}_remote",
        description=SPECS[name].description,
        agent_card=card,
        httpx_client=client,
        before_agent_callback=before,
        after_agent_callback=after,
    )


async def _run_team(inputs: dict, base: str, run_id: int | None, shared: dict) -> dict:
    names = list(inputs)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(CALL_TIMEOUT, connect=5.0), headers=_auth_headers()
    ) as client:
        cards = await asyncio.gather(*[_load_card(client, base, n) for n in names])
        team = ParallelAgent(
            name="execution_team",
            description="Runs the execution agents (CrewAI, served over A2A) concurrently.",
            sub_agents=[_remote(n, card, client) for n, card in zip(names, cards)],
        )

        sessions = InMemorySessionService()
        session_id = f"run-{run_id}-{uuid.uuid4().hex[:8]}"
        # The shared context, as ADK session state.
        await sessions.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=session_id,
            state={"run_id": run_id, **shared},
        )
        runner = Runner(agent=team, app_name=APP_NAME, session_service=sessions)
        message = types.Content(
            role="user",
            parts=[types.Part(text=json.dumps({**inputs, "run_id": run_id}, default=_json_default))],
        )

        replies: dict[str, str] = {}
        async for event in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=message):
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(p.text for p in event.content.parts if getattr(p, "text", None))
                if text:
                    replies[event.author.removesuffix("_remote")] = text

    missing = [n for n in names if n not in replies]
    if missing:
        raise RuntimeError(f"no reply over A2A from: {', '.join(missing)}")
    return {n: OUTPUT_CLASSES[n](**json.loads(replies[n])) for n in names}


def run_execution_team(
    inputs: dict, run_id: int | None = None, shared: dict | None = None, base_url: str | None = None
) -> dict:
    """Run the execution agents through the ADK team and return their outputs by name.

    `inputs` maps an agent name to its request ({"brief", "budget"}, plus
    "segments" and "previous" for crm). Synchronous, for the worker thread that
    is running the plan.
    """
    base = (base_url or a2a_base_url()).rstrip("/")
    return asyncio.run(_run_team(inputs, base, run_id, shared or {}))
