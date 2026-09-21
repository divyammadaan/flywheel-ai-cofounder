"""Structured logging of every agent decision -- observability, and what the
front end reads back.

The rows now live in `storage/`, which speaks both SQLite and Postgres. This
module stays as the import surface the engine, the CLIs, the MCP server and
the dashboard already use, so none of them had to change.

One behavioural change, and it is deliberate:

**`reset_records()` no longer deletes anything.** It used to empty the whole
table, so starting a plan destroyed the previous one with no confirmation and
no way back. It now opens a *new run*; reads are scoped to the current run, so
every caller sees exactly what it saw before, while the earlier plan survives
and becomes history the founder can go back to.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from storage import db as _db
from storage.records import add_record, fetch_records
from storage.runs import current_run_id, start_run

# Kept as a module attribute because observability/usage.py reads it at call
# time, and tests monkeypatch it to point at a temporary file.
DB_PATH = _db.DEFAULT_SQLITE_PATH


@dataclass
class DecisionRecord:
    cycle: int
    agent: str
    input_snapshot: dict
    decision: dict
    reasoning: str = ""
    confidence: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def log_decision(record: DecisionRecord) -> int:
    """Persist a DecisionRecord in the current run and return its row id."""
    return add_record(
        cycle=record.cycle,
        agent=record.agent,
        input_snapshot=_jsonable(record.input_snapshot),
        decision=_jsonable(record.decision),
        reasoning=record.reasoning,
        confidence=record.confidence,
        timestamp=record.timestamp,
    )


def get_records(cycle: int | None = None, agent: str | None = None, run_id: int | None = None) -> list[dict]:
    """The current run's records, optionally filtered by cycle and/or agent.

    `input_snapshot` and `decision` come back as JSON strings, because that is
    what the dashboard and the MCP server already parse.
    """
    return fetch_records(cycle=cycle, agent=agent, run_id=run_id)


def reset_records() -> int:
    """Start a fresh history by opening a new run. Deletes nothing.

    Returns the new run id.
    """
    return start_run()


def current_run() -> int:
    return current_run_id()


def _jsonable(value):
    """A payload the JSON column can hold.

    Agent outputs are plain dicts of primitives, lists and nested dicts, but
    dataclass `__dict__`s occasionally carry something else (a pandas
    Timestamp, an enum). json's default= turns those into strings rather than
    failing the write and losing the record.
    """
    return json.loads(json.dumps(value or {}, default=str))
