"""The CLI agent trace: silent unless enabled, one readable line per event."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from observability import trace


def test_trace_is_silent_until_enabled(capsys, monkeypatch):
    monkeypatch.setattr(trace, "_enabled", False)
    trace.call("sales", "groq/x", 10, 5, 1.0, False)
    trace.decision("sales", {}, {})
    trace.note("START", "strategy")
    assert capsys.readouterr().out == ""


def test_trace_prints_calls_decisions_and_rejections(capsys, monkeypatch):
    monkeypatch.setattr(trace, "_enabled", True)
    trace.call("marketing", "groq/qwen", 812, 340, 2.34, False)
    trace.call("marketing", "groq/qwen", 0, 0, 0.0, True)
    trace.decision("marketing", {}, {})
    trace.decision("strategy_rejected", {"problems": ["price is 9x the reference"]}, {})
    out = capsys.readouterr().out
    assert "MODEL CALL" in out and "812 in" in out and "340 out" in out
    assert "CACHE" in out
    assert "SAVED" in out and "marketing" in out
    assert "REJECT" in out and "price is 9x the reference" in out


def test_trace_can_be_switched_off_by_environment(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_TRACE", "0")
    trace.enable()
    assert trace._enabled is False


def test_traced_prints_start_and_finished_around_an_agent(capsys, monkeypatch):
    monkeypatch.setattr(trace, "_enabled", True)

    @trace.traced("finance")
    def run(x):
        return x * 2

    assert run(21) == 42
    out = capsys.readouterr().out
    assert out.index("START") < out.index("FINISHED")
    assert "finance" in out and "no model call" in out


def test_traced_reports_a_failure_and_reraises(capsys, monkeypatch):
    monkeypatch.setattr(trace, "_enabled", True)

    @trace.traced("sales")
    def boom():
        raise ValueError("nope")

    try:
        boom()
    except ValueError:
        pass
    assert "FAILED" in capsys.readouterr().out


def test_traced_is_a_plain_call_when_tracing_is_off(capsys, monkeypatch):
    monkeypatch.setattr(trace, "_enabled", False)

    @trace.traced("sales")
    def run():
        return "ok"

    assert run() == "ok"
    assert capsys.readouterr().out == ""
