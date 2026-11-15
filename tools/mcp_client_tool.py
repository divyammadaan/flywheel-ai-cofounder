"""Client for Flywheel's MCP server (tools/mcp_server.py) over stdio -- a real,
separate-process MCP client/server pair (not the in-memory transport used in
tests/test_mcp_server.py), so the engine uses its tools through the standard
protocol instead of importing the code behind them.

`call_tools` opens one session and runs several calls in it: starting the server
process is the expensive part (a second or two), so a batch pays for it once.

MCP here is an upgrade, never a new way for a plan to fail. Callers that have a
local equivalent use `with_fallback`, which runs the MCP call and, if the server
cannot be started or answers badly, runs the local function instead.
FLYWHEEL_MCP_TOOLS=off turns the tools off entirely (the tests do).
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from observability import trace

SERVER_SCRIPT = str(Path(__file__).resolve().parent / "mcp_server.py")
CALL_TIMEOUT_SECONDS = 120


def mcp_enabled() -> bool:
    return os.environ.get("FLYWHEEL_MCP_TOOLS", "on").strip().lower() not in {"0", "off", "false", "no"}


def _unwrap(result) -> Any:
    """A tool's return value. FastMCP wraps list and scalar returns as {"result": ...}."""
    if getattr(result, "isError", False):
        detail = " ".join(getattr(block, "text", "") for block in (result.content or []))
        raise RuntimeError(f"MCP tool failed: {detail[:200]}")
    structured = result.structuredContent
    if structured is None:
        # A tool that returns a bare `dict` has no output schema, so FastMCP sends
        # the value only as JSON text in the content blocks.
        text = " ".join(getattr(block, "text", "") for block in (result.content or []))
        if not text.strip():
            raise RuntimeError("MCP tool returned nothing")
        return json.loads(text)
    if isinstance(structured, dict) and set(structured) == {"result"}:
        return structured["result"]
    return structured


async def _call_many(calls: list[tuple[str, dict]]) -> list[Any]:
    # The whole environment is passed on: by default the MCP client forwards only a
    # few variables, so the server would read the default database instead of the
    # one this process is configured with.
    params = StdioServerParameters(command=sys.executable, args=[SERVER_SCRIPT], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            results = await asyncio.wait_for(
                asyncio.gather(*[session.call_tool(name, args) for name, args in calls]),
                timeout=CALL_TIMEOUT_SECONDS,
            )
            return [_unwrap(r) for r in results]


def call_tools(calls: list[tuple[str, dict]]) -> list[Any]:
    """Call several tools in one MCP session and return their results in order."""
    names = ", ".join(name for name, _ in calls)
    trace.note("MCP", f"calling {names} on the MCP server")
    results = asyncio.run(_call_many(calls))
    trace.note("MCP", f"{names} returned")
    return results


def call_tool(name: str, args: dict) -> Any:
    return call_tools([(name, args)])[0]


def with_fallback(tool: str, args: dict, local: Callable[..., Any]) -> Any:
    """The MCP tool's answer, or the local function's if MCP is off or fails."""
    if mcp_enabled():
        try:
            return call_tool(tool, args)
        except Exception as exc:  # noqa: BLE001 - see the module docstring
            trace.note("ERROR", f"MCP tool {tool} failed ({type(exc).__name__}); using the local function")
    return local(**args)


async def _query(agent: str | None, cycle: int | None) -> list[dict]:
    return (await _call_many([("query_decision_records", {"agent": agent, "cycle": cycle})]))[0]


def query_decision_records(agent: str | None = None, cycle: int | None = None) -> list[dict]:
    """Decision Records filtered by agent and/or cycle, fetched over MCP."""
    return asyncio.run(_query(agent, cycle))
