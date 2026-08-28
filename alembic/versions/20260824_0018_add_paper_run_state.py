"""Add paper_run_state for simulation node progress.

Revision ID: 20260824_0018
Revises: 20260824_0017
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0018"
down_revision: str | None = "20260824_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_run_state",
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cycles_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bars_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_cycle_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_bar_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("paper_run_state")
