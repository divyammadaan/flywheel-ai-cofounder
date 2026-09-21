"""Reading and writing decision records, scoped to a run."""

import json
from datetime import datetime, timezone

from sqlalchemy import delete, select

from storage.db import session_scope
from storage.models import DecisionRecordRow
from storage.runs import current_run_id


def add_record(
    cycle: int,
    agent: str,
    input_snapshot: dict,
    decision: dict,
    reasoning: str = "",
    confidence: float | None = None,
    timestamp: str | None = None,
    run_id: int | None = None,
) -> int:
    # Before the write scope: resolving the run may have to open one.
    target = run_id if run_id is not None else current_run_id()
    with session_scope(write=True) as session:
        row = DecisionRecordRow(
            run_id=target,
            cycle=cycle,
            agent=agent,
            input_snapshot=input_snapshot or {},
            reasoning=reasoning or "",
            decision=decision or {},
            confidence=confidence,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        )
        session.add(row)
        session.flush()
        return row.id


def fetch_records(
    cycle: int | None = None,
    agent: str | None = None,
    run_id: int | None = None,
    as_json_text: bool = True,
) -> list[dict]:
    """Records for one run, oldest first.

    `as_json_text` keeps `input_snapshot` and `decision` as JSON *strings*,
    which is the shape the dashboard and the MCP server already parse
    themselves. The API asks for `False` and gets real dicts.
    """
    target = run_id if run_id is not None else current_run_id()
    query = select(DecisionRecordRow).where(DecisionRecordRow.run_id == target)
    if cycle is not None:
        query = query.where(DecisionRecordRow.cycle == cycle)
    if agent is not None:
        query = query.where(DecisionRecordRow.agent == agent)
    query = query.order_by(DecisionRecordRow.id.asc())

    with session_scope() as session:
        return [_as_dict(row, as_json_text) for row in session.scalars(query).all()]


def clear_records(run_id: int | None = None) -> None:
    """Empty one run's records. Used by tests; production opens a new run."""
    target = run_id if run_id is not None else current_run_id()
    with session_scope(write=True) as session:
        session.execute(delete(DecisionRecordRow).where(DecisionRecordRow.run_id == target))


def _as_dict(row: DecisionRecordRow, as_json_text: bool) -> dict:
    snapshot, decision = row.input_snapshot, row.decision
    return {
        "id": row.id,
        "run_id": row.run_id,
        "cycle": row.cycle,
        "agent": row.agent,
        "input_snapshot": json.dumps(snapshot) if as_json_text else snapshot,
        "reasoning": row.reasoning,
        "decision": json.dumps(decision) if as_json_text else decision,
        "confidence": row.confidence,
        "timestamp": row.timestamp,
    }
