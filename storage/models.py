"""The database schema.

Five tables, and the reason each exists:

- **workspaces** -- who a run belongs to. Everything Flywheel stores is a
  founder's own business description, financials and customer list, so the
  moment two people share an instance, nothing may be readable across the
  boundary. Scoping is introduced here rather than retrofitted later, because
  retrofitting means auditing every query.
- **users** -- unused until login is added. The column exists now so that
  adding auth is a login screen and a session lookup, not a migration of every
  existing row.
- **runs** -- one founder working through one business, start to finish. This
  replaces the old "one global table, wiped on every start" design: starting a
  fresh plan now opens a new run instead of deleting the previous one.
- **decision_records** / **llm_usage** -- unchanged in meaning, now scoped to
  a run.
- **run_events** -- ordered progress for a run, so a founder who reloads
  mid-plan rejoins where they were instead of watching it start over.

`cycle` keeps its old meaning *within* a run: 0 (PRECYCLE) for the one-off
intake/research/advisor stage, then 1..n for each planned period.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None) -> str | None:
    """A datetime as an ISO string that always carries its UTC offset.

    SQLite has no timezone type: `DateTime(timezone=True)` writes an aware
    datetime but reads back a naive one, so `.isoformat()` produced
    "2026-09-20T16:50:22" with no offset. A browser parses that as LOCAL time,
    which put every timestamp 5.5 hours in the past here -- a run created
    seconds ago was labelled "6h ago". The values were always UTC; this says
    so explicitly.
    """
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    """A tenant. One seeded local workspace until login exists."""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    runs: Mapped[list["Run"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class User(Base):
    """Deliberately unused until auth lands -- see the module docstring."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # Null until a password is set: the seeded local user has no login.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Run(Base):
    """One business being planned, from intake through to a funding roadmap."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    # "new_idea" or "existing_business" -- set from BusinessInput.mode once
    # Intake has classified it, so it is null while a run is still starting.
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # queued | running | awaiting_answers | done | failed | blocked
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    # Why a run stopped, in the founder's terms (a PlanBlocked message).
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    workspace: Mapped[Workspace] = relationship(back_populates="runs")
    records: Mapped[list["DecisionRecordRow"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class DecisionRecordRow(Base):
    """One agent's decision, with the input it was given.

    input_snapshot and decision are JSON columns rather than TEXT: on Postgres
    that is real jsonb. The compatibility shim in observability/decision_record
    still hands callers JSON *strings*, because the dashboard and the MCP
    server parse them themselves and changing that is a Phase 3 concern.
    """

    __tablename__ = "decision_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    cycle: Mapped[int] = mapped_column(Integer, nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reasoning: Mapped[str | None] = mapped_column(Text, default="")
    decision: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[str] = mapped_column(String(64), nullable=False)

    run: Mapped[Run] = relationship(back_populates="records")


# The dashboard filters by agent within a run on every rerun.
Index("ix_decision_records_run_agent", DecisionRecordRow.run_id, DecisionRecordRow.agent)


class LlmUsageRow(Base):
    """Tokens, time and cache hits per model call.

    Written from several threads at once: the planning agents fan out in
    parallel and litellm reports from its own logging thread.
    """

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    calls: Mapped[int] = mapped_column(Integer, default=1)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    seconds: Mapped[float] = mapped_column(Float, default=0.0)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[str] = mapped_column(String(64), nullable=False)


class RunEvent(Base):
    """Progress from a run, in order.

    Persisted rather than pushed straight to the browser, and this is the
    point: a plan takes minutes, so the founder will switch tabs, reload, or
    lose their connection. Because every step is a row, a reconnecting client
    asks for everything after the last sequence number it saw and catches up,
    instead of watching a progress bar that restarted at zero.

    `seq` is per run and assigned by the writer, so clients can order and
    de-duplicate without depending on the global id.
    """

    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # started | agent_started | agent_finished | awaiting_answers | blocked |
    # failed | finished
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("ix_run_events_run_seq", RunEvent.run_id, RunEvent.seq, unique=True)
