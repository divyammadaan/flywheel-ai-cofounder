"""Client for Flywheel's MCP server (tools/mcp_server.py) over stdio -- a real,
separate-process MCP client/server pair (not the in-memory transport used in
tests/test_mcp_server.py), so code queries Decision Record history through
the standard protocol instead of importing observability code directly.

Used by the planning engine to fetch last period's CRM record. The CRM model
used to call this as a CrewAI tool itself, but on a 4B local model that added
a whole extra model call per run; see agents/crm.py.
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER_SCRIPT = str(Path(__file__).resolve().parent / "mcp_server.py")


async def _query(agent: str | None, cycle: int | None) -> list[dict]:
    params = StdioServerParameters(command=sys.executable, args=[SERVER_SCRIPT])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("query_decision_records", {"agent": agent, "cycle": cycle})
            return result.structuredContent["result"]


def query_decision_records(agent: str | None = None, cycle: int | None = None) -> list[dict]:
    """Decision Records filtered by agent and/or cycle, fetched over MCP."""
    return asyncio.run(_query(agent, cycle))
