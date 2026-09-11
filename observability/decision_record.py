"""Structured logging of every agent decision for observability + the dashboard."""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "flywheel.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decision_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle INTEGER NOT NULL,
    agent TEXT NOT NULL,
    input_snapshot TEXT NOT NULL,
    reasoning TEXT,
    decision TEXT NOT NULL,
    confidence REAL,
    timestamp TEXT NOT NULL
);
"""


@dataclass
class DecisionRecord:
    cycle: int
    agent: str
    input_snapshot: dict
    decision: dict
    reasoning: str = ""
    confidence: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def log_decision(record: DecisionRecord) -> int:
    """Persist a DecisionRecord and return its row id."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO decision_records (cycle, agent, input_snapshot, reasoning, decision, confidence, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.cycle,
                record.agent,
                json.dumps(record.input_snapshot),
                record.reasoning,
                json.dumps(record.decision),
                record.confidence,
                record.timestamp,
            ),
        )
        return cur.lastrowid


def get_records(cycle: int | None = None, agent: str | None = None) -> list[dict]:
    """Fetch decision records, optionally filtered by cycle and/or agent."""
    query = "SELECT * FROM decision_records"
    clauses, params = [], []
    if cycle is not None:
        clauses.append("cycle = ?")
        params.append(cycle)
    if agent is not None:
        clauses.append("agent = ?")
        params.append(agent)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id ASC"

    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
