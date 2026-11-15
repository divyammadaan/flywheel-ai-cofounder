"""Tests for the A2A bridge.

These deliberately avoid starting a server or calling an LLM -- they cover
the parts that actually broke during development: the Agent Card contract,
the response-shape parsing, and the fallback path.
"""

import json
import sys
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from agents._brief import PlanBrief
from orchestration.a2a_bridge import _extract_text, build_agent_card, server_is_up


def test_agent_card_advertises_the_marketing_skill():
    card = build_agent_card()
    assert card.name == "flywheel-marketing"
    skill_ids = {s.id for s in card.skills}
    assert "plan_campaigns" in skill_ids


def test_agent_card_example_is_valid_json_matching_the_executor_contract():
    """The example in the card is what another agent would copy. If it drifts
    from the keys MarketingExecutor actually reads, discovery is misleading."""
    card = build_agent_card()
    example = json.loads(card.skills[0].examples[0])
    assert set(example) == {"budget", "brief"}
    assert set(example["brief"]) == {f.name for f in fields(PlanBrief)}


def test_extract_text_handles_direct_message_shape():
    """What a direct (non-task) reply looks like -- this exact shape was
    being dropped, silently forcing every call onto the fallback path."""
    result = {"message": {"role": "ROLE_AGENT", "parts": [{"text": '{"ok": true}'}]}}
    assert _extract_text(result) == '{"ok": true}'


def test_extract_text_handles_task_status_shape():
    result = {"status": {"message": {"parts": [{"text": "from-status"}]}}}
    assert _extract_text(result) == "from-status"


def test_extract_text_handles_history_shape():
    result = {"history": [{"parts": [{"text": "from-history"}]}]}
    assert _extract_text(result) == "from-history"


def test_extract_text_raises_rather_than_returning_empty():
    with pytest.raises(RuntimeError):
        _extract_text({"message": {"parts": [{"data": "no text here"}]}})


def test_server_is_up_is_false_when_nothing_is_listening():
    """Discovery must fail fast and cleanly on a dead port, otherwise the
    fallback never triggers and the engine stalls."""
    assert server_is_up("http://127.0.0.1:9") is False


# ---------------------------------------------------- the four-agent team --

import asyncio
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import httpx

from agents.crm import CRMOutput
from agents.marketing import MarketingOutput
from agents.product import ProductOutput
from agents.sales import SalesOutput
from orchestration import a2a_bridge
from orchestration.a2a_bridge import AGENT_NAMES, SPECS, ExecutionExecutor
from orchestration.adk_coordinator import a2a_enabled, run_execution_team
from storage import current_run_id, start_run


def test_every_execution_agent_publishes_a_card_that_says_where_to_send_requests():
    assert AGENT_NAMES == ("marketing", "sales", "product", "crm")
    for name in AGENT_NAMES:
        card = build_agent_card(name, "http://example.test/a2a")
        assert card.name == f"flywheel-{name}"
        (interface,) = card.supported_interfaces
        assert interface.url == f"http://example.test/a2a/{name}/a2a"
        assert card.skills[0].id == SPECS[name].skill_id


def test_a2a_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_A2A", "off")
    assert a2a_enabled("http://127.0.0.1:9") is False


def test_a2a_is_not_used_when_the_agents_are_not_being_served(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_A2A", "auto")
    assert a2a_enabled("http://127.0.0.1:9") is False


def _fake_output(name, budget):
    common = dict(cycle=1, budget=budget, currency="INR")
    if name == "marketing":
        return MarketingOutput(**common, campaigns=[], ad_copy="copy", image_prompt="p", ad_image_path=None)
    if name == "sales":
        return SalesOutput(**common, lead_sources=[], conversion_process=["call"])
    if name == "product":
        return ProductOutput(**common, plan_type="inventory", line_items=[], line_items_total=0.0,
                             sourcing_plan=[], replenish_policy=[], cost_basis="x")
    return CRMOutput(**common, segments={"best": 1}, changes={}, actions={}, spend={}, budget_adjusted=False,
                     slipping_message="m", lost_message="m", message_previews=[])


def _fake_agent_class(name, seen):
    class Fake:
        def execute(self, brief, budget, *extra):
            seen[name] = {"brief_summary": brief.business_summary, "budget": budget, "extra": extra, "run": current_run_id()}
            return _fake_output(name, budget)

    return Fake


def _serve_team(monkeypatch, seen):
    """The real A2A app and the real ADK coordinator, with stand-in agents (no model)."""
    import uvicorn

    for name in AGENT_NAMES:
        monkeypatch.setitem(SPECS, name, replace(SPECS[name], agent_class=_fake_agent_class(name, seen)))
    port = 8793
    base = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(a2a_bridge.create_app(base), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(80):
        try:
            if httpx.get(f"{base}/marketing/.well-known/agent-card.json", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    return base, server, thread


def test_the_adk_coordinator_runs_the_four_agents_over_a2a_and_returns_typed_outputs(monkeypatch):
    seen = {}
    base, server, thread = _serve_team(monkeypatch, seen)
    try:
        run = start_run(mode="existing_business")
        brief = PlanBrief(
            cycle=1, mode="operate", business_summary="Coffee in Bangalore", industry="F&B", product_or_service="coffee",
            region="Bangalore", currency="INR", positioning="fresh", target_customer="professionals", price=899.0, price_unit="per month",
        )
        from dataclasses import asdict

        inputs = {n: {"brief": asdict(brief), "budget": float(i + 1) * 100} for i, n in enumerate(AGENT_NAMES)}
        inputs["crm"].update({"segments": {"best": 3}, "previous": None})

        results = run_execution_team(inputs, run_id=run, shared={"brief": asdict(brief)}, base_url=base)
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    assert isinstance(results["marketing"], MarketingOutput) and isinstance(results["crm"], CRMOutput)
    assert isinstance(results["sales"], SalesOutput) and isinstance(results["product"], ProductOutput)
    assert results["sales"].budget == 200.0  # each agent got its own slice of the request
    assert seen["crm"]["extra"][0] == {"best": 3}  # crm also received the segments
    # The run travelled in the message, so the agents worked under the right run.
    assert {s["run"] for s in seen.values()} == {run}


def test_the_executor_reads_its_own_slice_and_binds_the_run():
    seen = {}
    name = "sales"
    original = SPECS[name]
    SPECS[name] = replace(original, agent_class=_fake_agent_class(name, seen))
    try:
        run = start_run(mode="new_idea")
        queue = SimpleNamespace(events=[])

        async def enqueue(event):
            queue.events.append(event)

        queue.enqueue_event = enqueue
        brief = {f: getattr(_EXAMPLE, f) for f in _EXAMPLE.__dataclass_fields__}
        text = json.dumps({"run_id": run, "sales": {"brief": brief, "budget": 50}, "marketing": {"brief": brief, "budget": 999}})
        asyncio.run(ExecutionExecutor(name).execute(SimpleNamespace(get_user_input=lambda: text), queue))
    finally:
        SPECS[name] = original

    assert seen["sales"]["budget"] == 50.0 and seen["sales"]["run"] == run
    assert json.loads(queue.events[0].parts[0].text)["budget"] == 50.0


_EXAMPLE = a2a_bridge._EXAMPLE_BRIEF


def test_a_failing_a2a_team_falls_back_to_the_in_process_agents(monkeypatch):
    from orchestration import cycle

    monkeypatch.setattr(cycle, "a2a_enabled", lambda: True)

    def broken(*a, **k):
        raise RuntimeError("a2a down")

    monkeypatch.setattr(cycle, "run_execution_team", broken)
    monkeypatch.setattr(cycle, "request_marketing", lambda brief, budget: (_fake_output("marketing", budget), "direct"))
    monkeypatch.setattr(cycle, "ProductAgent", lambda: SimpleNamespace(execute=lambda b, bud: _fake_output("product", bud)))
    monkeypatch.setattr(cycle, "SalesAgent", lambda: SimpleNamespace(execute=lambda b, bud: _fake_output("sales", bud)))
    allocation = SimpleNamespace(marketing=10.0, product=20.0, sales=30.0, crm=0.0)
    briefs = {n: _EXAMPLE for n in ("marketing", "product", "sales")}

    marketing, transport, outputs = cycle._run_execution_agents(
        ("marketing", "product", "sales"), briefs, allocation, _EXAMPLE, None, 1
    )
    assert transport == "direct" and set(outputs) == {"product", "sales"}
