"""Flywheel's persistence layer.

One code path over SQLite and Postgres, chosen by `FLYWHEEL_DATABASE_URL`.
It defaults to the project's own SQLite file, so the CLIs, the MCP server and
the test suite need no database running.

`observability/decision_record.py` remains the import surface the engine and
the dashboard use; it forwards here.
"""

from storage.db import (
    ENV_VAR,
    DEFAULT_SQLITE_PATH,
    database_url,
    default_url,
    dispose,
    get_engine,
    is_sqlite,
    session_scope,
)
from storage.events import FINAL_KINDS, add_event, fetch_events, latest_seq
from storage.records import add_record, clear_records, fetch_records
from storage.runs import (
    LOCAL_WORKSPACE_SLUG,
    current_run_id,
    delete_run,
    get_run,
    latest_run_id,
    list_runs,
    local_workspace_id,
    set_current_run,
    start_run,
    update_run,
    using_run,
)
from storage.usage import add_usage, clear_usage, fetch_usage

__all__ = [
    "DEFAULT_SQLITE_PATH",
    "ENV_VAR",
    "FINAL_KINDS",
    "LOCAL_WORKSPACE_SLUG",
    "add_event",
    "add_record",
    "add_usage",
    "clear_records",
    "clear_usage",
    "current_run_id",
    "database_url",
    "default_url",
    "delete_run",
    "dispose",
    "fetch_events",
    "fetch_records",
    "fetch_usage",
    "get_engine",
    "get_run",
    "is_sqlite",
    "latest_run_id",
    "latest_seq",
    "list_runs",
    "local_workspace_id",
    "session_scope",
    "set_current_run",
    "start_run",
    "update_run",
    "using_run",
]
