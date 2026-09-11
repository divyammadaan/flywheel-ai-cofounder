"""Flywheel's MCP server — exposes Decision Record history as MCP tools so
any agent (regardless of framework) can query run history through the same
standard protocol interface, instead of importing observability code
directly.

Run standalone (stdio transport, for use with an MCP-compatible client):
    python tools/mcp_server.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from observability.decision_record import get_records

mcp = FastMCP(
    name="flywheel-decision-records",
    instructions="Query Flywheel's Decision Record history: what each agent decided, and why, per cycle.",
)


def _parse_record(record: dict) -> dict:
    """get_records() stores decision/input_snapshot as raw JSON text; parse
    them back to dicts so MCP clients get structured data, not JSON-in-a-
    string."""
    parsed = dict(record)
    parsed["input_snapshot"] = json.loads(record["input_snapshot"])
    parsed["decision"] = json.loads(record["decision"])
    return parsed


@mcp.tool()
def query_decision_records(cycle: int | None = None, agent: str | None = None) -> list[dict]:
    """Return Decision Records, optionally filtered by cycle and/or agent name.

    Args:
        cycle: only return records from this cycle number, if given.
        agent: only return records from this agent (e.g. "strategy", "finance",
            "marketing", "product", "sales", "crm", "analytics", "simulator"),
            if given.
    """
    return [_parse_record(r) for r in get_records(cycle=cycle, agent=agent)]


@mcp.tool()
def get_latest_analytics_summary() -> str | None:
    """Return the most recent cycle's Analytics natural-language summary, or
    None if no cycles have run yet."""
    records = [_parse_record(r) for r in get_records(agent="analytics")]
    if not records:
        return None
    latest = max(records, key=lambda r: r["cycle"])
    return latest["decision"].get("summary")


if __name__ == "__main__":
    mcp.run(transport="stdio")
