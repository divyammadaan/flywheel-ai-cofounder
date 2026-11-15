"""Add run_assets: files a run produced (the ad image), kept in the database.

A hosted server's disk is wiped on restart, so the image cannot live only on it.

Revision ID: 0004_run_assets
Revises: 0003_run_events
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_run_assets"
down_revision = "0003_run_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "run_assets" in sa.inspect(op.get_bind()).get_table_names():
        return

    op.create_table(
        "run_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_run_assets_run_id", "run_assets", ["run_id"])


def downgrade() -> None:
    op.drop_table("run_assets")
