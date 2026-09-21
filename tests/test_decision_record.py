"""The Decision Record store: run scoping, and the Windows file-locking
behaviour that shaped its connection handling.

Each test gets its own empty database from the autouse fixture in conftest.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from observability.decision_record import DecisionRecord, get_records, log_decision, reset_records
from observability.usage import record_usage, usage_summary
from storage import db as storage_db
from storage import delete_run, get_run, list_runs, start_run, update_run, using_run


def test_a_fresh_start_gives_an_empty_history():
    log_decision(DecisionRecord(1, "strategy", {}, {"price": 899}))
    record_usage("strategy", "m", 100, 20, 0.5)

    reset_records()

    assert get_records() == []
    assert usage_summary(settle_seconds=0)["agents"] == []


def test_a_fresh_start_keeps_the_previous_plan_instead_of_deleting_it():
    """The point of runs.

    reset_records() used to empty the whole table, so starting a plan
    destroyed the founder's previous one with no confirmation and no way back.
    It now opens a new run: the new one reads empty, the old one is still
    there in full.
    """
    first = reset_records()
    log_decision(DecisionRecord(1, "strategy", {}, {"price": 899}))

    second = reset_records()
    log_decision(DecisionRecord(1, "strategy", {}, {"price": 1099}))

    assert second != first
    assert len(get_records()) == 1
    assert get_records()[0]["run_id"] == second

    earlier = get_records(run_id=first)
    assert len(earlier) == 1
    assert '"price": 899' in earlier[0]["decision"]


def test_records_are_filtered_by_cycle_and_agent_within_a_run():
    reset_records()
    log_decision(DecisionRecord(0, "intake", {}, {"a": 1}))
    log_decision(DecisionRecord(1, "strategy", {}, {"b": 2}))
    log_decision(DecisionRecord(1, "finance", {}, {"c": 3}))

    assert [r["agent"] for r in get_records(cycle=1)] == ["strategy", "finance"]
    assert [r["agent"] for r in get_records(agent="intake")] == ["intake"]


def test_usage_is_scoped_to_its_run_too():
    first = reset_records()
    record_usage("strategy", "m", 100, 20, 0.5)

    reset_records()
    record_usage("marketing", "m", 50, 10, 0.2)

    agents = usage_summary(settle_seconds=0)["agents"]
    assert [a["agent"] for a in agents] == ["marketing"]

    with using_run(first):
        assert [a["agent"] for a in usage_summary(settle_seconds=0)["agents"]] == ["strategy"]


def test_using_run_restores_the_previous_run_afterwards():
    outer = reset_records()
    inner = start_run()

    with using_run(outer):
        log_decision(DecisionRecord(1, "strategy", {}, {}))

    # Back in `inner`, which never received that record.
    log_decision(DecisionRecord(1, "finance", {}, {}))
    assert [r["agent"] for r in get_records()] == ["finance"]
    assert [r["agent"] for r in get_records(run_id=outer)] == ["strategy"]


def test_a_run_carries_its_status_and_error():
    run_id = reset_records()
    update_run(run_id, status="blocked", error="The reserve uses all the capital.")

    run = get_run(run_id)
    assert run["status"] == "blocked"
    assert run["error"] == "The reserve uses all the capital."


def test_update_run_rejects_a_field_it_does_not_own():
    run_id = reset_records()
    with pytest.raises(ValueError, match="workspace_id"):
        update_run(run_id, workspace_id=999)


def test_deleting_a_run_takes_its_records_with_it():
    """ON DELETE CASCADE is silently ignored on SQLite unless the foreign-keys
    pragma is on, which would leave orphaned records behind."""
    doomed = reset_records()
    log_decision(DecisionRecord(1, "strategy", {}, {}))
    keeper = start_run()
    log_decision(DecisionRecord(1, "finance", {}, {}))

    delete_run(doomed)

    assert get_records(run_id=doomed) == []
    assert len(get_records(run_id=keeper)) == 1
    assert [r["id"] for r in list_runs()] == [keeper]


def test_the_database_file_is_released_once_the_engine_is_disposed(tmp_path, monkeypatch):
    """The dashboard once crashed with WinError 32 because reads left
    connections open, and a fresh run tried to delete the file underneath
    them. Nothing deletes the database any more, but the pool must still let
    go on request -- otherwise no test could clean up its temp file either.
    """
    path = tmp_path / "released.db"
    monkeypatch.setenv(storage_db.ENV_VAR, f"sqlite:///{path.as_posix()}")
    storage_db.dispose()

    log_decision(DecisionRecord(1, "strategy", {}, {"price": 899}))
    get_records()
    record_usage("strategy", "m", 100, 20, 0.5)
    usage_summary(settle_seconds=0)

    storage_db.dispose()
    path.unlink()

    assert not path.exists()
