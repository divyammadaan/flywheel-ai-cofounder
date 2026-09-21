"""Adopt pre-run decision records and usage rows into a run.

A database created before run scoping has `decision_records` and `llm_usage`
without a `run_id`, holding one founder's real plan. Dropping those rows would
delete their work, so this migration adds the column, creates a workspace and
a single "Imported" run, and points every existing row at it.

Order matters: the column is added nullable, backfilled, and only then made
NOT NULL -- adding it NOT NULL outright fails on a table that already has rows.

Revision ID: 0002_adopt_legacy_rows
Revises: 0001_baseline
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0002_adopt_legacy_rows"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

LEGACY_RUN_LABEL = "Imported from before run history"


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    needs_backfill = [t for t in ("decision_records", "llm_usage") if "run_id" not in _columns(t)]
    if not needs_backfill:
        return

    now = datetime.now(timezone.utc)

    workspace_id = bind.execute(sa.text("SELECT id FROM workspaces WHERE slug = 'local'")).scalar()
    if workspace_id is None:
        bind.execute(
            sa.text(
                "INSERT INTO workspaces (slug, name, created_at) VALUES ('local', 'My workspace', :now)"
            ),
            {"now": now},
        )
        workspace_id = bind.execute(sa.text("SELECT id FROM workspaces WHERE slug = 'local'")).scalar()

    bind.execute(
        sa.text(
            "INSERT INTO runs (workspace_id, mode, label, status, created_at, updated_at) "
            "VALUES (:ws, NULL, :label, 'done', :now, :now)"
        ),
        {"ws": workspace_id, "label": LEGACY_RUN_LABEL, "now": now},
    )
    run_id = bind.execute(
        sa.text("SELECT id FROM runs WHERE workspace_id = :ws ORDER BY id DESC"), {"ws": workspace_id}
    ).scalar()

    for table in needs_backfill:
        # Nullable first: the table already has rows, so a NOT NULL column
        # with no default cannot be added directly.
        op.add_column(table, sa.Column("run_id", sa.Integer(), nullable=True))
        bind.execute(sa.text(f"UPDATE {table} SET run_id = :run_id"), {"run_id": run_id})
        with op.batch_alter_table(table) as batch:
            batch.alter_column("run_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(
                f"fk_{table}_run_id", "runs", ["run_id"], ["id"], ondelete="CASCADE"
            )
        op.create_index(f"ix_{table}_run_id", table, ["run_id"])

    if "decision_records" in needs_backfill:
        op.create_index("ix_decision_records_run_agent", "decision_records", ["run_id", "agent"])


def downgrade() -> None:
    for table in ("decision_records", "llm_usage"):
        if "run_id" in _columns(table):
            op.drop_column(table, "run_id")
