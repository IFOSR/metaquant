"""Add research kind + test/backtest/paper fields to strategy drafts.

Revision ID: 20260826_0022
Revises: 20260826_0021
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260826_0022"
down_revision: str | None = "20260826_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strategy_drafts",
        sa.Column(
            "kind",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'strategy'"),
        ),
    )
    op.add_column(
        "strategy_drafts",
        sa.Column("code_test_result", sa.JSON(), nullable=True),
    )
    op.add_column(
        "strategy_drafts",
        sa.Column(
            "backtest_results",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "strategy_drafts",
        sa.Column("paper_binding", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strategy_drafts", "paper_binding")
    op.drop_column("strategy_drafts", "backtest_results")
    op.drop_column("strategy_drafts", "code_test_result")
    op.drop_column("strategy_drafts", "kind")
