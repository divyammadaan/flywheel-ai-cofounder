"""CrewAI tool that talks to Flywheel's MCP server (tools/mcp_server.py)
over stdio -- a real, separate-process MCP client/server pair (not the
in-memory transport used in tests/test_mcp_server.py), so any CrewAI agent
can query Decision Record history through the standard protocol instead of
importing observability code directly.
"""

import asyncio
import sys
from pathlib import Path

from crewai.tools import BaseTool
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import BaseModel, Field

SERVER_SCRIPT = str(Path(__file__).resolve().parent / "mcp_server.py")


class DecisionRecordQueryInput(BaseModel):
    agent: str | None = Field(default=None, description="Filter by agent name, e.g. 'analytics'")
    cycle: int | None = Field(default=None, description="Filter by cycle number")


class DecisionRecordQueryTool(BaseTool):
    name: str = "query_decision_records"
    description: str = (
        "Query Flywheel's Decision Record history over MCP -- what agents decided in past "
        "cycles, and why. Useful for grounding a decision in this run's actual history "
        "instead of only what's in the current prompt."
    )
    args_schema: type[BaseModel] = DecisionRecordQueryInput

    def _run(self, agent: str | None = None, cycle: int | None = None) -> str:
        return asyncio.run(self._query(agent, cycle))

    async def _query(self, agent: str | None, cycle: int | None) -> str:
        params = StdioServerParameters(command=sys.executable, args=[SERVER_SCRIPT])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("query_decision_records", {"agent": agent, "cycle": cycle})
                return str(result.structuredContent["result"])
