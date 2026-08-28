"""Create backtest_tasks for async strategy backtest runs.

Revision ID: 20260824_0019
Revises: 20260824_0018
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0019"
down_revision: str | None = "20260824_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result_address", sa.String(128), nullable=True),
        sa.Column("error", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_backtest_tasks_owner", "backtest_tasks", ["owner"])
    op.create_index("ix_backtest_tasks_status", "backtest_tasks", ["status"])


def downgrade() -> None:
    op.drop_table("backtest_tasks")
