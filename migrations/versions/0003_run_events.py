"""Add run_events: ordered progress a reconnecting client can catch up on.

Revision ID: 0003_run_events
Revises: 0002_adopt_legacy_rows
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_run_events"
down_revision = "0002_adopt_legacy_rows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "run_events" in sa.inspect(op.get_bind()).get_table_names():
        return

    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("agent", sa.String(64), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    # Unique: two agents finishing at the same moment must not share a seq,
    # or a client would silently drop one while de-duplicating.
    op.create_index("ix_run_events_run_seq", "run_events", ["run_id", "seq"], unique=True)


def downgrade() -> None:
    op.drop_table("run_events")
