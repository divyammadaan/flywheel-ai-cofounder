"""Engine and session handling, for SQLite and Postgres from one code path.

`FLYWHEEL_DATABASE_URL` picks the backend. It defaults to the same SQLite file
the project has always used, so the CLIs, the MCP server and the test suite are
unaffected and the course demo needs no database running. The API sets it to
Postgres.

Two details that are not optional on Windows:

- **Connections are closed, not just committed.** `with sqlite3.connect(...)`
  only commits; the file stays locked until garbage collection, which is what
  made a fresh dashboard run fail with WinError 32 while its own earlier reads
  still held the file. Every session here is closed in a `finally`.
- **SQLite is reached from several threads.** The planning agents fan out in
  parallel and litellm logs from its own thread, so `check_same_thread` is off
  and writes are serialised by the lock in `session_scope`.
"""

import os
import threading
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from storage.models import Base

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "flywheel.db"
ENV_VAR = "FLYWHEEL_DATABASE_URL"

# SQLite has no row-level locking, so concurrent writers raise "database is
# locked" rather than queueing. The planning fan-out writes from four threads
# at once, so writes are serialised here. Postgres does not need this, but
# holding it costs nothing at this scale.
#
# RLock, not Lock: one write can legitimately open another on the same thread
# -- opening a run seeds its workspace first -- and a plain Lock deadlocks on
# itself there.
_write_lock = threading.RLock()

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_configured_url: str | None = None


def default_url() -> str:
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"


def database_url() -> str:
    return os.environ.get(ENV_VAR) or default_url()


def is_sqlite(url: str | None = None) -> bool:
    return (url or database_url()).startswith("sqlite")


def _create_engine(url: str) -> Engine:
    if is_sqlite(url):
        path = url.replace("sqlite:///", "", 1)
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            # WAL lets the dashboard read while a run is still writing.
            cursor.execute("PRAGMA journal_mode=WAL")
            # Without this, ON DELETE CASCADE is silently ignored on SQLite,
            # and deleting a run would orphan its records instead of removing
            # them.
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    # pool_pre_ping: a pooled Postgres connection that died while the process
    # sat idle between runs is replaced instead of raising on first use.
    return create_engine(url, future=True, pool_pre_ping=True)


def get_engine() -> Engine:
    """The process-wide engine, rebuilt if the configured URL changed.

    The rebuild is what lets a test point FLYWHEEL_DATABASE_URL at a temporary
    file mid-process without having to reach into module internals.
    """
    global _engine, _session_factory, _configured_url
    url = database_url()
    if _engine is None or url != _configured_url:
        dispose()
        _engine = _create_engine(url)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
        _configured_url = url
        Base.metadata.create_all(_engine)
    return _engine


def dispose() -> None:
    """Drop the engine and close its pooled connections.

    Needed on Windows before a test's temporary database file can be removed,
    and whenever the configured URL changes.
    """
    global _engine, _session_factory, _configured_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _configured_url = None


@contextmanager
def session_scope(write: bool = False):
    """A session that commits on success, rolls back on failure, always closes.

    `write=True` takes the serialising lock described in the module docstring.
    """
    get_engine()
    assert _session_factory is not None
    session = _session_factory()
    lock = _write_lock if write and is_sqlite() else None
    if lock:
        lock.acquire()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        if lock:
            lock.release()
