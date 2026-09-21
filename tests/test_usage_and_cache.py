"""Token accounting and the response cache -- no model involved."""

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import agents._cache as cache_mod
import observability.usage as usage_mod
from observability.usage import record_usage, usage_summary


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    # The database is isolated by the autouse fixture in conftest.py.
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / "llm_cache")
    monkeypatch.setattr(usage_mod, "_install_litellm_hook", lambda: None)
    monkeypatch.setattr(usage_mod, "_ROLE_TO_AGENT", {})
    monkeypatch.setenv("FLYWHEEL_LLM_CACHE", "1")


@dataclass
class Answer:
    text: str


def _agent_class():
    class Agent:
        model_name = "test-model"

        def __init__(self):
            self.calls = 0

        @cache_mod.cached("tester", Answer)
        def run(self, prompt: str) -> Answer:
            self.calls += 1
            return Answer(text=prompt.upper())

    return Agent


def _litellm_call(prompt: str, prompt_tokens: int, completion_tokens: int):
    start = datetime(2026, 9, 15, 12, 0, 0)
    usage_mod._on_litellm_success(
        {"messages": [{"role": "user", "content": prompt}], "model": "groq/qwen"},
        SimpleNamespace(usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)),
        start,
        start + timedelta(seconds=1.5),
    )


def test_usage_is_summed_per_agent():
    record_usage("marketing", "m", 400, 200, 1.5)
    record_usage("marketing", "m", 100, 50, 0.5)
    record_usage("sales", "m", 300, 150, 1.0)
    summary = usage_summary(settle_seconds=0)
    marketing = summary["agents"][0]
    assert (marketing["agent"], marketing["calls"], marketing["prompt_tokens"], marketing["completion_tokens"]) == (
        "marketing", 2, 500, 250,
    )
    assert summary["totals"]["completion_tokens"] == 400


def test_crewai_calls_are_attributed_by_the_role_that_opens_the_prompt():
    usage_mod.register_role("Marketing Lead", "marketing", "groq/qwen")
    usage_mod.register_role("Sales Lead", "sales", "groq/qwen")
    # Other roles mentioned later in the prompt must not confuse attribution.
    _litellm_call("SYSTEM: You are Marketing Lead. Lean startup. USER: context mentions the Sales Lead", 506, 34)
    agents = usage_summary(settle_seconds=0)["agents"]
    assert [(a["agent"], a["prompt_tokens"], a["completion_tokens"]) for a in agents] == [("marketing", 506, 34)]


def test_calls_from_unregistered_prompts_are_ignored():
    _litellm_call("You are the Strategy agent for Flywheel.", 900, 100)
    assert usage_summary(settle_seconds=0)["agents"] == []


def test_identical_inputs_reuse_the_saved_answer():
    agent = _agent_class()()
    assert agent.run("hello") == Answer("HELLO")
    assert agent.run("hello") == Answer("HELLO")
    assert agent.calls == 1
    assert usage_summary(settle_seconds=0)["totals"]["cache_hits"] == 1


def test_different_inputs_are_not_confused():
    agent = _agent_class()()
    agent.run("hello")
    assert agent.run("goodbye") == Answer("GOODBYE")
    assert agent.calls == 2


def test_cache_key_follows_the_agent_file_not_the_retry_decorator():
    """Agent methods are wrapped by retry_on_rate_limit, whose wrapper lives in
    agents/_retry.py. The key must hash the agent's own file, or editing an
    agent's prompt would replay answers written by the old prompt."""
    from agents._retry import retry_on_rate_limit

    @retry_on_rate_limit()
    def run():
        return None

    assert Path(cache_mod._source_file(run)).name == "test_usage_and_cache.py"


def test_a_result_the_agent_rejects_is_not_saved():
    class Agent:
        model_name = "test-model"

        def __init__(self):
            self.calls = 0

        @cache_mod.cached("tester", Answer, should_cache=lambda result: result.text != "FAILED")
        def run(self, prompt: str) -> Answer:
            self.calls += 1
            return Answer(text="FAILED")

    agent = Agent()
    agent.run("hello")
    agent.run("hello")
    assert agent.calls == 2


def test_caching_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_LLM_CACHE", "0")
    agent = _agent_class()()
    agent.run("hello")
    agent.run("hello")
    assert agent.calls == 2
