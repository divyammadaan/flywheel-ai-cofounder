"""The Decision Record store's lifecycle on Windows, where an open SQLite
connection locks the file."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import observability.decision_record as decision_record_module
from observability.decision_record import DecisionRecord, get_records, log_decision, reset_records
from observability.usage import record_usage, usage_summary


def test_reset_clears_decisions_and_usage(tmp_path, monkeypatch):
    monkeypatch.setattr(decision_record_module, "DB_PATH", tmp_path / "flywheel.db")
    log_decision(DecisionRecord(1, "strategy", {}, {"price": 899}))
    record_usage("strategy", "m", 100, 20, 0.5)

    reset_records()

    assert get_records() == []
    assert usage_summary(settle_seconds=0)["agents"] == []


def test_connections_are_closed_so_the_file_is_not_left_locked(tmp_path, monkeypatch):
    """The dashboard crashed with WinError 32 because reads left connections
    open. Deleting the file fails on Windows if any connection is still open."""
    path = tmp_path / "flywheel.db"
    monkeypatch.setattr(decision_record_module, "DB_PATH", path)
    log_decision(DecisionRecord(1, "strategy", {}, {"price": 899}))
    get_records()
    record_usage("strategy", "m", 100, 20, 0.5)
    usage_summary(settle_seconds=0)

    path.unlink()

    assert not path.exists()
