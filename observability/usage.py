"""LLM usage per agent: calls, tokens, time and cache hits.

Every model call is recorded here, so a run shows where its tokens went and
what the response cache saved. Stored in the same SQLite file as the Decision
Records, so it is cleared with them when a fresh run starts.

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
import sqlite3
import threading
import time
from datetime import datetime, timezone

from observability import decision_record

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    model TEXT,
    calls INTEGER NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    seconds REAL NOT NULL,
    cached INTEGER NOT NULL,
    timestamp TEXT NOT NULL
);
"""
# The planning agents run in parallel threads, and litellm reports from its
# own logging thread; all of them write here.
_lock = threading.Lock()

_ROLE_TO_AGENT: dict[str, tuple[str, str | None]] = {}
_CREW_PROMPT_ROLE = re.compile(r"^\s*SYSTEM:\s*You are (.+?)\.")
_hook_installed = False


def _connect() -> sqlite3.Connection:
    path = decision_record.DB_PATH  # read at call time, so tests can point it elsewhere
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    return conn


def record_usage(
    agent: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    seconds: float,
    calls: int = 1,
    cached: bool = False,
) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO llm_usage (agent, model, calls, prompt_tokens, completion_tokens, seconds, cached, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                agent,
                model,
                int(calls),
                int(prompt_tokens or 0),
                int(completion_tokens or 0),
                round(float(seconds), 2),
                int(bool(cached)),
                datetime.now(timezone.utc).isoformat(),
            ),
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


def _row_count() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0]


def usage_summary(settle_seconds: float = 3.0) -> dict:
    """Per-agent totals for the current run, in the order agents first ran.

    litellm reports CrewAI calls from a background thread, so the last few
    rows can land just after a run finishes; wait (up to `settle_seconds`)
    for the row count to stop changing before summarising.
    """
    deadline = time.monotonic() + settle_seconds
    count, stable_since = _row_count(), time.monotonic()
    while time.monotonic() < deadline and time.monotonic() - stable_since < 1.0:
        time.sleep(0.25)
        current = _row_count()
        if current != count:
            count, stable_since = current, time.monotonic()

    with _connect() as conn:
        rows = conn.execute(
            "SELECT agent, SUM(CASE WHEN cached = 0 THEN calls ELSE 0 END), SUM(cached), "
            "SUM(prompt_tokens), SUM(completion_tokens), SUM(seconds) "
            "FROM llm_usage GROUP BY agent ORDER BY MIN(id)"
        ).fetchall()
    agents = [
        {
            "agent": agent,
            "calls": int(calls or 0),
            "cache_hits": int(hits or 0),
            "prompt_tokens": int(prompt or 0),
            "completion_tokens": int(completion or 0),
            "seconds": round(float(seconds or 0), 1),
        }
        for agent, calls, hits, prompt, completion, seconds in rows
    ]
    totals = {key: sum(a[key] for a in agents) for key in ("calls", "cache_hits", "prompt_tokens", "completion_tokens")}
    totals["seconds"] = round(sum(a["seconds"] for a in agents), 1)
    return {"agents": agents, "totals": totals}
