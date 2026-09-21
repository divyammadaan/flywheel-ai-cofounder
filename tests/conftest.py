"""Every test gets its own empty database, and no worker outlives it.

Before the storage layer existed, tests reached in and monkeypatched
`decision_record.DB_PATH`. Any test that forgot wrote into the real
`data/flywheel.db` and polluted the founder's own history. Pointing
`FLYWHEEL_DATABASE_URL` at a temp file per test makes that impossible to get
wrong, and is also how the API is configured in production -- so the suite
exercises the same switch.

The background pool is torn down in the *same* fixture, and before the engine
is disposed. Order matters and was learned the hard way: a job still running
when the environment variable was restored re-opened the engine against the
default URL and wrote its result into the real database.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage import db as storage_db  # noqa: E402
from storage import runs as storage_runs  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """A fresh SQLite file per test, torn down after it.

    Autouse, so it is set up first and finalised last -- which is what puts
    the worker shutdown below ahead of the environment being restored.
    """
    monkeypatch.setenv(storage_db.ENV_VAR, f"sqlite:///{(tmp_path / 'flywheel.db').as_posix()}")
    _reset_workers()
    # The engine is cached per URL, so drop the previous test's: on Windows an
    # open pooled connection keeps the temp file locked and cleanup fails.
    storage_db.dispose()
    storage_runs.set_current_run(None)

    yield

    # Workers first: one still in flight would otherwise be writing while the
    # engine is torn down, and would land in the real database.
    _reset_workers(wait=True)
    storage_db.dispose()
    storage_runs.set_current_run(None)


def _reset_workers(wait: bool = False) -> None:
    """Stop the API's job pool, if this test run imported it at all.

    Imported lazily so the storage and agent tests don't pull in FastAPI.
    """
    if "api.jobs" not in sys.modules:
        return
    sys.modules["api.jobs"].shutdown(wait=wait)
