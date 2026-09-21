"""LLM usage per agent: calls, tokens, time and cache hits.

Every model call is recorded here, so a run shows where its tokens went and
what the response cache saved. Rows are scoped to a run, alongside the Decision
Records, so a summary reports the run it belongs to rather than everything the
database has ever seen.

How each framework's calls get counted -- measured, because the obvious
sources turned out to be empty:
- CrewAI agents: CrewAI's own counters (the kickoff result's token_usage, the
  crew's usage_metrics, the LLM's usage summary) all read 0 after a real Groq
  call with structured output. litellm's success callback does receive the
  real token counts, but it runs on litellm's logging thread and drops any
  metadata we attach -- so the call is attributed from its prompt instead:
  CrewAI starts every prompt with "SYSTEM: You are <role>.", and each agent
  registers its role (register_role).
- ADK agents (Strategy, Analytics): ADK puts usage on each response event;
  they call record_adk_usage.
- CRM: Ollama returns token counts in its response; it calls record_usage.
"""

import re
import threading
import time

from storage.usage import add_usage, fetch_usage, usage_row_count

# The planning agents run in parallel threads, and litellm reports from its
# own logging thread; all of them write here.
_lock = threading.Lock()

_ROLE_TO_AGENT: dict[str, tuple[str, str | None]] = {}
_CREW_PROMPT_ROLE = re.compile(r"^\s*SYSTEM:\s*You are (.+?)\.")
_hook_installed = False


def record_usage(
    agent: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    seconds: float,
    calls: int = 1,
    cached: bool = False,
) -> None:
    """Record one model call against the current run.

    The lock is still held here: the planning agents fan out in parallel and
    litellm reports from its own logging thread, so several callers reach this
    at once.
    """
    with _lock:
        add_usage(
            agent=agent,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            seconds=seconds,
            calls=calls,
            cached=cached,
        )


# ---------------------------------------------------------------- CrewAI --


def register_role(role: str, agent: str, model: str | None = None) -> None:
    """Tell the usage hook that prompts from this CrewAI role belong to `agent`."""
    _ROLE_TO_AGENT[role] = (agent, model)
    _install_litellm_hook()


def _install_litellm_hook() -> None:
    global _hook_installed
    if _hook_installed:
        return
    import litellm

    if _on_litellm_success not in litellm.success_callback:
        litellm.success_callback.append(_on_litellm_success)
    _hook_installed = True


def agent_for_messages(messages) -> tuple[str, str | None] | None:
    """Which registered agent sent these messages, from CrewAI's opening line."""
    for message in messages or []:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
        match = _CREW_PROMPT_ROLE.match(str(content or ""))
        if match:
            return _ROLE_TO_AGENT.get(match.group(1).strip())
    return None


def _on_litellm_success(kwargs, response, start_time, end_time) -> None:
    try:
        found = agent_for_messages(kwargs.get("messages"))
        if found is None:
            return  # not a CrewAI agent of ours; ADK and CRM report their own usage
        agent, model = found
        usage = getattr(response, "usage", None)
        record_usage(
            agent,
            model or kwargs.get("model"),
            getattr(usage, "prompt_tokens", 0),
            getattr(usage, "completion_tokens", 0),
            (end_time - start_time).total_seconds(),
        )
    except Exception:  # noqa: BLE001 - bookkeeping must never break a model call
        pass


# ------------------------------------------------------------------- ADK --


def record_adk_usage(agent: str, model: str | None, usage_metadata: list, started: float) -> None:
    """ADK reports token counts on each model response (event.usage_metadata)."""
    prompt = sum((getattr(u, "prompt_token_count", 0) or 0) for u in usage_metadata)
    completion = sum((getattr(u, "candidates_token_count", 0) or 0) for u in usage_metadata)
    record_usage(agent, model, prompt, completion, time.perf_counter() - started, calls=max(len(usage_metadata), 1))


# --------------------------------------------------------------- summary --


def usage_summary(settle_seconds: float = 3.0) -> dict:
    """Per-agent totals for the current run, in the order agents first ran.

    litellm reports CrewAI calls from a background thread, so the last few
    rows can land just after a run finishes; wait (up to `settle_seconds`)
    for the row count to stop changing before summarising.
    """
    deadline = time.monotonic() + settle_seconds
    count, stable_since = usage_row_count(), time.monotonic()
    while time.monotonic() < deadline and time.monotonic() - stable_since < 1.0:
        time.sleep(0.25)
        current = usage_row_count()
        if current != count:
            count, stable_since = current, time.monotonic()

    agents = fetch_usage()
    totals = {key: sum(a[key] for a in agents) for key in ("calls", "cache_hits", "prompt_tokens", "completion_tokens")}
    totals["seconds"] = round(sum(a["seconds"] for a in agents), 1)
    return {"agents": agents, "totals": totals}
