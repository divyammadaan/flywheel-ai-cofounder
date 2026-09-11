import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import observability.decision_record as decision_record_module
from mcp.shared.memory import create_connected_server_and_client_session
from observability.decision_record import DecisionRecord, log_decision
from tools.mcp_server import mcp


@pytest.fixture(autouse=True)
def seed_records(tmp_path, monkeypatch):
    # Isolate each test on its own DB file -- decision_record.py otherwise
    # writes to the real data/flywheel.db, so records would accumulate
    # across test runs and leak between tests.
    monkeypatch.setattr(decision_record_module, "DB_PATH", tmp_path / "test_flywheel.db")

    log_decision(DecisionRecord(1, "strategy", {"previous_summary": None}, {"positioning": "launch", "pricing": 40.0}))
    log_decision(DecisionRecord(1, "analytics", {}, {"summary": "Cycle 1 went fine."}))
    log_decision(DecisionRecord(2, "analytics", {}, {"summary": "Cycle 2 improved on cycle 1."}))


@pytest.mark.anyio
async def test_tools_are_discoverable():
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        tools = (await client.list_tools()).tools
        tool_names = {t.name for t in tools}
        assert "query_decision_records" in tool_names
        assert "get_latest_analytics_summary" in tool_names


@pytest.mark.anyio
async def test_query_decision_records_filters_by_agent():
    # Read structuredContent, not content[0].text: the latter is a legacy
    # plain-text fallback that (confirmed via manual inspection) unwraps a
    # single-item list to a bare object instead of a one-element array.
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.call_tool("query_decision_records", {"agent": "strategy"})
        payload = result.structuredContent["result"]
        assert len(payload) == 1
        assert payload[0]["agent"] == "strategy"
        assert payload[0]["decision"]["positioning"] == "launch"


@pytest.mark.anyio
async def test_get_latest_analytics_summary_returns_most_recent_cycle():
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.call_tool("get_latest_analytics_summary", {})
        summary = result.structuredContent["result"]
        assert "cycle 2" in summary.lower()
