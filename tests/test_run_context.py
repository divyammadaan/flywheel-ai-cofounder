"""The parallel planning stage must write to the run it belongs to."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestration.cycle import submit_in_context
from storage.runs import current_run_id, start_run, using_run


def test_a_pool_thread_sees_the_callers_run_not_the_newest_run():
    mine = start_run(mode="existing_business")
    newest = start_run(mode="new_idea")  # a later run: what any context-less thread falls back to
    assert newest > mine

    with using_run(mine), ThreadPoolExecutor(max_workers=2) as pool:
        futures = [submit_in_context(pool, current_run_id) for _ in range(4)]
        assert [f.result() for f in futures] == [mine] * 4


def test_without_the_copied_context_a_pool_thread_falls_back_to_the_newest_run():
    mine = start_run(mode="existing_business")
    newest = start_run(mode="new_idea")
    with using_run(mine), ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(current_run_id).result() == newest  # the bug submit_in_context fixes


def test_a_failing_mcp_lookup_does_not_fail_the_plan(monkeypatch):
    from orchestration import cycle

    def broken(**kwargs):
        raise RuntimeError("Connection closed")

    monkeypatch.setattr(cycle, "query_decision_records", broken)
    assert cycle.previous_segments(2) is None
