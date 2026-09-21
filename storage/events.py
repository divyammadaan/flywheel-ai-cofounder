"""Progress events for a run.

Events are rows, not an in-memory queue, so the API can answer "what happened
after event 7?" for a client that reconnected. Nothing is lost when a browser
reloads, a tab sleeps or the server restarts mid-plan.
"""

from sqlalchemy import func, select

from storage.db import session_scope
from storage.models import RunEvent, utc_iso
from storage.runs import current_run_id

# Terminal kinds: a client can stop listening once it sees one of these.
FINAL_KINDS = frozenset({"finished", "failed", "blocked", "awaiting_answers"})


def add_event(
    kind: str,
    agent: str | None = None,
    message: str | None = None,
    payload: dict | None = None,
    run_id: int | None = None,
) -> dict:
    """Append an event and return it.

    `seq` is allocated inside the write scope so two agents finishing at the
    same moment cannot claim the same number -- the fan-out means that races
    genuinely happen.
    """
    target = run_id if run_id is not None else current_run_id()
    with session_scope(write=True) as session:
        next_seq = (
            session.scalar(select(func.max(RunEvent.seq)).where(RunEvent.run_id == target)) or 0
        ) + 1
        event = RunEvent(
            run_id=target,
            seq=next_seq,
            kind=kind,
            agent=agent,
            message=message,
            payload=payload or {},
        )
        session.add(event)
        session.flush()
        return _as_dict(event)


def fetch_events(run_id: int, after_seq: int = 0, limit: int = 500) -> list[dict]:
    """Everything after `after_seq`, oldest first -- the catch-up query."""
    with session_scope() as session:
        events = session.scalars(
            select(RunEvent)
            .where(RunEvent.run_id == run_id, RunEvent.seq > after_seq)
            .order_by(RunEvent.seq.asc())
            .limit(limit)
        ).all()
        return [_as_dict(e) for e in events]


def latest_seq(run_id: int) -> int:
    with session_scope() as session:
        return int(session.scalar(select(func.max(RunEvent.seq)).where(RunEvent.run_id == run_id)) or 0)


def _as_dict(event: RunEvent) -> dict:
    return {
        "seq": event.seq,
        "run_id": event.run_id,
        "kind": event.kind,
        "agent": event.agent,
        "message": event.message,
        "payload": event.payload or {},
        "created_at": utc_iso(event.created_at),
    }
