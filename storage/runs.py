"""Workspaces and runs: what a decision record belongs to.

Before this, Flywheel had one global table and starting a plan called
`reset_records()`, which deleted everything with no confirmation. That made
two things impossible at once -- two people using one instance, and one person
keeping two businesses -- and it silently destroyed the previous plan.

A run replaces that. `start_run()` opens a new one; everything written
afterwards is scoped to it, and the previous run stays exactly where it was.
Nothing is deleted to start something new.

**The current run is per thread.** The API serves several founders at once and
must never let one request's writes land in another's run, so the active run is
held in a `ContextVar` rather than a module global. A thread that has not set
one (a CLI, the MCP server, a test) falls back to the newest run in the local
workspace, which is what makes the old call sites keep working untouched.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import select

from storage.db import session_scope
from storage.models import Run, User, Workspace, utc_iso

# The single tenant everything belongs to until login exists.
LOCAL_WORKSPACE_SLUG = "local"
LOCAL_WORKSPACE_NAME = "My workspace"
LOCAL_USER_EMAIL = "local@flywheel.invalid"

_current_run_id: ContextVar[int | None] = ContextVar("flywheel_current_run_id", default=None)


def local_workspace_id() -> int:
    """The seeded local workspace, created on first use."""
    with session_scope(write=True) as session:
        workspace = session.scalar(select(Workspace).where(Workspace.slug == LOCAL_WORKSPACE_SLUG))
        if workspace is None:
            workspace = Workspace(slug=LOCAL_WORKSPACE_SLUG, name=LOCAL_WORKSPACE_NAME)
            session.add(workspace)
            session.flush()
            # Seeded with no password: there is no login yet, and this row
            # exists so that adding one later is not a schema migration.
            session.add(User(workspace_id=workspace.id, email=LOCAL_USER_EMAIL, name="Local user"))
        return workspace.id


def start_run(mode: str | None = None, label: str | None = None, workspace_id: int | None = None) -> int:
    """Open a new run and make it the current one for this thread."""
    # Resolved before the write scope opens, not inside it: seeding the
    # workspace is itself a write.
    target_workspace = workspace_id if workspace_id is not None else local_workspace_id()
    with session_scope(write=True) as session:
        run = Run(
            workspace_id=target_workspace,
            mode=mode,
            label=label,
            status="running",
        )
        session.add(run)
        session.flush()
        run_id = run.id
    _current_run_id.set(run_id)
    return run_id


def latest_run_id(workspace_id: int | None = None) -> int | None:
    """The newest run in a workspace, or None when it has none yet."""
    ws = workspace_id if workspace_id is not None else local_workspace_id()
    with session_scope() as session:
        return session.scalar(select(Run.id).where(Run.workspace_id == ws).order_by(Run.id.desc()).limit(1))


def current_run_id() -> int:
    """The run this thread is writing to, opening one if there is none.

    The fallback to the newest existing run is what keeps every pre-existing
    caller working: a CLI that never mentions runs still appends to, and reads
    back, the run it started.
    """
    run_id = _current_run_id.get()
    if run_id is not None:
        return run_id
    run_id = latest_run_id()
    if run_id is None:
        return start_run()
    _current_run_id.set(run_id)
    return run_id


def set_current_run(run_id: int | None) -> None:
    _current_run_id.set(run_id)


@contextmanager
def using_run(run_id: int):
    """Scope a block of work to a run, restoring the previous one afterwards.

    The API uses this so a background worker writes into the run it was handed
    without leaking that choice into whatever the thread does next.
    """
    token = _current_run_id.set(run_id)
    try:
        yield run_id
    finally:
        _current_run_id.reset(token)


def get_run(run_id: int) -> dict | None:
    with session_scope() as session:
        run = session.get(Run, run_id)
        return _as_dict(run) if run else None


def list_runs(workspace_id: int | None = None, limit: int = 50) -> list[dict]:
    """Runs newest first -- the history the old global table couldn't keep."""
    ws = workspace_id if workspace_id is not None else local_workspace_id()
    with session_scope() as session:
        runs = session.scalars(
            select(Run).where(Run.workspace_id == ws).order_by(Run.id.desc()).limit(limit)
        ).all()
        return [_as_dict(r) for r in runs]


def update_run(run_id: int, **fields) -> None:
    """Set any of mode, label, status or error on a run."""
    allowed = {"mode", "label", "status", "error"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown run fields: {', '.join(sorted(unknown))}")
    with session_scope(write=True) as session:
        run = session.get(Run, run_id)
        if run is None:
            raise LookupError(f"no run with id {run_id}")
        for key, value in fields.items():
            setattr(run, key, value)


def delete_run(run_id: int) -> None:
    """Remove a run and its records. The only destructive call in the module."""
    with session_scope(write=True) as session:
        run = session.get(Run, run_id)
        if run is not None:
            session.delete(run)
    if _current_run_id.get() == run_id:
        _current_run_id.set(None)


def _as_dict(run: Run) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "mode": run.mode,
        "label": run.label,
        "status": run.status,
        "error": run.error,
        "created_at": utc_iso(run.created_at),
        "updated_at": utc_iso(run.updated_at),
    }
