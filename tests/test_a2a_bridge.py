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
