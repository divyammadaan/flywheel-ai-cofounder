"""Live agent trace for the command line.

The CLI flows (orchestration/validate_flow.py, review_flow.py) turn this on, and
every agent decision and every model call prints one line as it happens, so a
run can be watched agent by agent:

    [  4.0s] START      market_research   calling groq/qwen/qwen3.8-27b
    [  6.3s] MODEL CALL market_research   groq/qwen/qwen3.8-27b    812 in /  340 out   2.3s
    [  6.3s] FINISHED   market_research   2.3s
    [  6.4s] SAVED      market_research   decision record saved
    [ 11.0s] REJECT     strategy          price is 9x the reference price
    [ 31.5s] PARALLEL   marketing, product, sales, crm run at the same time

It hooks the two places every agent already reports to -- log_decision
(observability/decision_record.py) and record_usage (observability/usage.py) --
so no agent needed to change. Off by default (tests stay quiet); the CLI flows
and the API server turn it on, and FLYWHEEL_TRACE=0 turns it off in both.
"""

import functools
import os
import threading
import time

_lock = threading.Lock()
_enabled = False
_wall_clock = False
_started = time.monotonic()


def enable(wall_clock: bool = False) -> None:
    """Start printing. Called by the entry points (CLI flows, API server), not by library code.

    The CLI stamps seconds since the run began. The API server runs many plans
    over its lifetime, so it stamps the time of day instead.
    """
    global _enabled, _started, _wall_clock
    _enabled = os.environ.get("FLYWHEEL_TRACE", "1") != "0"
    _wall_clock = wall_clock
    _started = time.monotonic()


def disable() -> None:
    global _enabled
    _enabled = False


def _emit(tag: str, text: str) -> None:
    stamp = time.strftime("%H:%M:%S") if _wall_clock else f"{time.monotonic() - _started:6.1f}s"
    # The planning agents run in parallel threads, so one lock keeps each line whole.
    with _lock:
        print(f"[{stamp}] {tag:<12}{text}", flush=True)


def note(tag: str, text: str) -> None:
    if _enabled:
        _emit(tag, text)


def call(agent: str, model: str | None, prompt_tokens: int, completion_tokens: int, seconds: float, cached: bool) -> None:
    """One model call (or one answer reused from the cache)."""
    if not _enabled:
        return
    if cached:
        _emit("CACHE", f"{agent:<18}answer reused, no model call")
        return
    _emit("MODEL CALL", f"{agent:<18}{(model or '-'):<26}{prompt_tokens:>5} in /{completion_tokens:>5} out  {seconds:>5.1f}s")


def decision(agent: str, input_snapshot: dict, decision_payload: dict) -> None:
    """An agent's result was saved. A `<agent>_rejected` record is a guardrail refusal."""
    if not _enabled:
        return
    if agent.endswith("_rejected"):
        problems = (input_snapshot or {}).get("problems") or []
        _emit("REJECT", f"{agent.removesuffix('_rejected'):<18}{' '.join(problems)[:160]}")
        return
    _emit("SAVED", f"{agent:<18}decision record saved")


# Finance sits in AGENT_MODELS but never calls a model: it is arithmetic.
_NO_MODEL = {"finance"}


def _what(name: str) -> str:
    if name in _NO_MODEL:
        return "arithmetic in code (MCP cash calculator), no model call"
    from agents._models import AGENT_MODELS  # lazy: agents import this module

    model = AGENT_MODELS.get(name)
    if not model:
        return ""
    return f"calling {model}"


def traced(name: str):
    """Print when an agent starts and when it finishes, around its entry method.

    Put it outermost on the method (above @cached and @retry_on_rate_limit) so
    START is the moment the agent is called, and FINISHED includes any retries.
    The MODEL CALL line for the same agent prints in between, when the reply
    comes back.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _enabled:
                return fn(*args, **kwargs)
            _emit("START", f"{name:<18}{_what(name)}")
            started = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                _emit("FAILED", f"{name:<18}{type(exc).__name__} after {time.perf_counter() - started:.1f}s")
                raise
            _emit("FINISHED", f"{name:<18}{time.perf_counter() - started:.1f}s")
            return result

        return wrapper

    return decorator
