"""Baseline schema: workspaces, users, runs, decision records, llm usage.

Creates each table only if it is missing, because this project already has
databases in the wild -- a founder's own `data/flywheel.db` from before
migrations existed, holding real decision records. Those get the new tables
here and their existing rows adopted into a run by 0002.

Revision ID: 0001_baseline
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _existing_tables()

    if "workspaces" not in tables:
        op.create_table(
            "workspaces",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("slug", sa.String(64), nullable=False, unique=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=True)

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("email", sa.String(320), nullable=False, unique=True),
            # Null until a password is set: there is no login yet.
            sa.Column("password_hash", sa.String(255), nullable=True),
            sa.Column("name", sa.String(200), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        op.create_index("ix_users_workspace_id", "users", ["workspace_id"])

    if "runs" not in tables:
        op.create_table(
            "runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("mode", sa.String(32), nullable=True),
            sa.Column("label", sa.String(300), nullable=True),
            sa.Column("status", sa.String(32), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_runs_workspace_id", "runs", ["workspace_id"])
        op.create_index("ix_runs_status", "runs", ["status"])

    if "decision_records" not in tables:
        op.create_table(
            "decision_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("cycle", sa.Integer(), nullable=False),
            sa.Column("agent", sa.String(64), nullable=False),
            sa.Column("input_snapshot", sa.JSON(), nullable=False),
            sa.Column("reasoning", sa.Text(), nullable=True),
            sa.Column("decision", sa.JSON(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("timestamp", sa.String(64), nullable=False),
        )
        op.create_index("ix_decision_records_run_id", "decision_records", ["run_id"])
        op.create_index("ix_decision_records_run_agent", "decision_records", ["run_id", "agent"])

    if "llm_usage" not in tables:
        op.create_table(
            "llm_usage",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("agent", sa.String(64), nullable=False),
            sa.Column("model", sa.String(200), nullable=True),
            sa.Column("calls", sa.Integer(), nullable=True),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("seconds", sa.Float(), nullable=True),
            sa.Column("cached", sa.Boolean(), nullable=True),
            sa.Column("timestamp", sa.String(64), nullable=False),
        )
        op.create_index("ix_llm_usage_run_id", "llm_usage", ["run_id"])


def downgrade() -> None:
    for table in ("llm_usage", "decision_records", "runs", "users", "workspaces"):
        op.drop_table(table)
