"""Add saved_versions to strategy drafts (save-at-any-step).

Revision ID: 20260826_0020
Revises: 20260824_0019
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260826_0020"
down_revision: str | None = "20260824_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strategy_drafts",
        sa.Column(
            "saved_versions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("strategy_drafts", "saved_versions")
