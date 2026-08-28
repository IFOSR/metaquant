"""Add backtest_plan to strategy drafts.

Revision ID: 20260824_0017
Revises: 20260822_0016
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0017"
down_revision: str | None = "20260822_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strategy_drafts",
        sa.Column("backtest_plan", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strategy_drafts", "backtest_plan")
