"""The storage layer's own contracts.

The interesting ones are the two that a single-user SQLite design never had to
hold: workspaces must actually separate tenants, and the write path must
survive the planning fan-out writing from several threads at once.
"""

import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from storage import (
    add_event,
    add_record,
    add_usage,
    current_run_id,
    fetch_records,
    fetch_usage,
    list_runs,
    local_workspace_id,
    session_scope,
    start_run,
    using_run,
)
from storage.db import database_url, default_url, is_sqlite
from storage.models import User, Workspace


def test_the_local_workspace_is_created_once_and_reused():
    first = local_workspace_id()
    second = local_workspace_id()
    assert first == second

    with session_scope() as session:
        assert len(session.scalars(select(Workspace)).all()) == 1


def test_the_local_workspace_seeds_a_user_row_for_auth_to_land_on_later():
    """Auth is deferred, but the row exists now so adding login is a login
    screen rather than a migration of every existing record."""
    workspace_id = local_workspace_id()
    with session_scope() as session:
        user = session.scalar(select(User).where(User.workspace_id == workspace_id))
    assert user is not None
    assert user.password_hash is None


def test_runs_in_different_workspaces_cannot_see_each_others_records():
    """The whole point of scoping: one founder's financials and customer list
    must never be readable from another's workspace."""
    with session_scope(write=True) as session:
        other = Workspace(slug="other", name="Someone else")
        session.add(other)
        session.flush()
        other_id = other.id

    mine = start_run()
    add_record(1, "strategy", {}, {"price": 899})

    theirs = start_run(workspace_id=other_id)
    add_record(1, "strategy", {}, {"price": 1})

    assert len(fetch_records(run_id=mine)) == 1
    assert len(fetch_records(run_id=theirs)) == 1
    assert [r["id"] for r in list_runs()] == [mine]
    assert [r["id"] for r in list_runs(workspace_id=other_id)] == [theirs]


def test_records_come_back_as_dicts_when_asked():
    """The dashboard parses JSON strings itself; the API wants real objects."""
    start_run()
    add_record(1, "strategy", {"mode": "launch"}, {"rationale": ["one", "two"]})

    as_text = fetch_records()[0]
    assert isinstance(as_text["decision"], str)

    as_objects = fetch_records(as_json_text=False)[0]
    assert as_objects["decision"] == {"rationale": ["one", "two"]}


def test_usage_counts_real_calls_and_cache_hits_separately():
    start_run()
    add_usage("strategy", "m", 100, 20, 1.0)
    add_usage("strategy", "m", 0, 0, 0.0, cached=True)

    row = fetch_usage()[0]
    assert row["calls"] == 1, "a cache hit is not a model call"
    assert row["cache_hits"] == 1
    assert row["prompt_tokens"] == 100


def test_usage_rows_are_ordered_by_when_each_agent_first_ran():
    start_run()
    add_usage("intake", "m", 10, 1, 0.1)
    add_usage("strategy", "m", 10, 1, 0.1)
    add_usage("intake", "m", 10, 1, 0.1)

    assert [r["agent"] for r in fetch_usage()] == ["intake", "strategy"]


def test_concurrent_writes_do_not_lose_rows_or_deadlock():
    """The planning agents fan out across threads, and litellm reports from
    its own. SQLite has no row-level locking, so without serialising the
    writes this raises "database is locked" and drops decisions.
    """
    run_id = start_run()
    errors: list[BaseException] = []

    def write(n: int) -> None:
        try:
            with using_run(run_id):
                add_record(1, f"agent_{n}", {}, {"n": n})
                add_usage(f"agent_{n}", "m", 10, 2, 0.1)
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"concurrent writes failed: {errors[:3]}"
    assert not any(t.is_alive() for t in threads), "a writer deadlocked"
    assert len(fetch_records(run_id=run_id)) == 12
    assert len(fetch_usage(run_id=run_id)) == 12


def test_a_thread_without_a_run_falls_back_to_the_newest_one():
    """What keeps every pre-existing caller working: the CLIs and the MCP
    server never mention runs, and must still read the run in progress."""
    run_id = start_run()
    seen: list[int] = []

    thread = threading.Thread(target=lambda: seen.append(current_run_id()))
    thread.start()
    thread.join(timeout=10)

    assert seen == [run_id]


def test_the_default_database_is_the_projects_own_sqlite_file(monkeypatch):
    """The course demo must keep working with no database configured."""
    monkeypatch.delenv("FLYWHEEL_DATABASE_URL", raising=False)
    assert database_url() == default_url()
    assert is_sqlite()


def test_a_postgres_url_is_not_treated_as_sqlite(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_DATABASE_URL", "postgresql+psycopg://u:p@localhost/flywheel")
    assert not is_sqlite()


def test_a_new_run_carries_the_mode_and_label_it_was_opened_with():
    run_id = start_run(mode="new_idea", label="Coffee subscription")
    runs = {r["id"]: r for r in list_runs()}
    assert runs[run_id]["mode"] == "new_idea"
    assert runs[run_id]["label"] == "Coffee subscription"
    assert runs[run_id]["status"] == "running"


def test_timestamps_always_carry_their_utc_offset():
    """SQLite has no timezone type, so an aware datetime reads back naive and
    `.isoformat()` drops the offset. A browser then parses it as LOCAL time --
    which labelled a run created seconds ago as "6h ago" on an IST machine.
    """
    run_id = start_run()
    created = list_runs()[0]["created_at"]

    assert created is not None
    parsed = datetime.fromisoformat(created)
    assert parsed.tzinfo is not None, "an offset-less timestamp is read as local time by clients"
    assert parsed.utcoffset() == timedelta(0)

    # Within a minute of now, which it cannot be if the offset were dropped.
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 60
    assert run_id


def test_event_timestamps_carry_their_offset_too():
    run_id = start_run()
    event = add_event("started", message="Run started", run_id=run_id)
    parsed = datetime.fromisoformat(event["created_at"])
    assert parsed.tzinfo is not None
