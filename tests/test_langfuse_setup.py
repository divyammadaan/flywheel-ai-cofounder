"""Langfuse tracing: switched on by environment, tags per agent, names masked for CRM."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from observability import langfuse_setup as lf
from storage import start_run, using_run


def test_off_without_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert not lf.enabled()
    assert lf.llm_metadata("sales") == {}
    assert lf.install() is False


def test_needs_both_keys(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    assert not lf.enabled()


def test_metadata_names_the_agent_and_the_run(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-x")
    run = start_run(mode="new_idea")
    with using_run(run):
        meta = lf.llm_metadata("marketing")["metadata"]
    assert meta["trace_name"] == "marketing" and meta["generation_name"] == "marketing"
    assert meta["session_id"] == f"run-{run}"
    assert "marketing" in meta["tags"]


def _call(agent, text="Rohan Mehta spent 12,000"):
    kwargs = {
        "litellm_params": {"metadata": {"trace_name": agent}},
        "messages": [{"role": "system", "content": "You run retention"}, {"role": "user", "content": text}],
    }
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Hi Rohan, come back"))])
    return kwargs, response


def test_crm_calls_are_masked_before_they_reach_langfuse_without_touching_the_originals():
    kwargs, response = _call("crm")
    safe_kwargs, safe_response = lf.masked(kwargs, response)
    assert all(m["content"] == lf.MASKED_TEXT for m in safe_kwargs["messages"])
    assert safe_response.choices[0].message.content == lf.MASKED_TEXT
    # The agent still reads the real reply, and the real prompt is unchanged.
    assert response.choices[0].message.content == "Hi Rohan, come back"
    assert kwargs["messages"][1]["content"] == "Rohan Mehta spent 12,000"


def test_other_agents_are_sent_as_they_are():
    kwargs, response = _call("marketing", "Plan campaigns")
    safe_kwargs, safe_response = lf.masked(kwargs, response)
    assert safe_kwargs is kwargs and safe_response is response  # already tagged: nothing to add


def test_an_uncopyable_crm_reply_sends_no_text_rather_than_the_real_text():
    kwargs, _ = _call("crm")

    class Uncopyable:
        choices = []

        def __deepcopy__(self, memo):
            raise RuntimeError("no copy")

    assert lf.masked(kwargs, Uncopyable())[1] is None


def test_an_untagged_crewai_call_is_attributed_from_its_prompt(monkeypatch):
    from observability.usage import register_role

    register_role("Customer Retention Lead", "crm", "groq/x")
    kwargs = {
        "litellm_params": {},
        "messages": [{"role": "system", "content": "SYSTEM: You are Customer Retention Lead. Your goal is x"}, {"role": "user", "content": "Rohan"}],
    }
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Hi Rohan"))])
    safe, safe_response = lf.masked(kwargs, response)
    assert safe["litellm_params"]["metadata"]["trace_name"] == "crm"
    # ...and being CRM, it is masked even though the call carried no tags of its own.
    assert safe["messages"][1]["content"] == lf.MASKED_TEXT
    assert safe_response.choices[0].message.content == lf.MASKED_TEXT
