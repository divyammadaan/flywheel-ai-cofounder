"""Model-usage rows, scoped to a run.

The aggregation lives here rather than in `observability/usage.py` so that the
SQL is written once against the ORM and works on both SQLite and Postgres.
"""

from datetime import datetime, timezone

from sqlalchemy import case, delete, func, select

from storage.db import session_scope
from storage.models import LlmUsageRow
from storage.runs import current_run_id


def add_usage(
    agent: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    seconds: float,
    calls: int = 1,
    cached: bool = False,
    run_id: int | None = None,
) -> None:
    # Before the write scope: resolving the run may have to open one.
    target = run_id if run_id is not None else current_run_id()
    with session_scope(write=True) as session:
        session.add(
            LlmUsageRow(
                run_id=target,
                agent=agent,
                model=model,
                calls=calls,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                seconds=seconds,
                cached=cached,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )


def usage_row_count(run_id: int | None = None) -> int:
    target = run_id if run_id is not None else current_run_id()
    with session_scope() as session:
        return int(session.scalar(select(func.count(LlmUsageRow.id)).where(LlmUsageRow.run_id == target)) or 0)


def fetch_usage(run_id: int | None = None) -> list[dict]:
    """Per-agent totals for one run, in the order the agents first ran.

    `calls` counts only real model calls; a cache hit costs nothing and is
    counted separately, so the two columns answer different questions.
    """
    target = run_id if run_id is not None else current_run_id()
    calls_made = func.sum(case((LlmUsageRow.cached.is_(False), LlmUsageRow.calls), else_=0))
    cache_hits = func.sum(case((LlmUsageRow.cached.is_(True), 1), else_=0))

    query = (
        select(
            LlmUsageRow.agent,
            calls_made,
            cache_hits,
            func.sum(LlmUsageRow.prompt_tokens),
            func.sum(LlmUsageRow.completion_tokens),
            func.sum(LlmUsageRow.seconds),
        )
        .where(LlmUsageRow.run_id == target)
        .group_by(LlmUsageRow.agent)
        .order_by(func.min(LlmUsageRow.id))
    )

    with session_scope() as session:
        rows = session.execute(query).all()

    return [
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


def clear_usage(run_id: int | None = None) -> None:
    target = run_id if run_id is not None else current_run_id()
    with session_scope(write=True) as session:
        session.execute(delete(LlmUsageRow).where(LlmUsageRow.run_id == target))
