"""Create natural-language strategy drafting tables.

Revision ID: 20260822_0015
Revises: 20260819_0014
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0015"
down_revision: str | None = "20260819_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_drafts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("ready", sa.Boolean(), nullable=False, default=False),
        sa.Column("instrument_ids", sa.JSON(), nullable=False),
        sa.Column("frequency", sa.String(16), nullable=False, default="1d"),
        sa.Column("content_hash", sa.String(80), nullable=True),
        sa.Column("resource_version", sa.Integer(), nullable=False, default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategy_drafts_owner", "strategy_drafts", ["owner"])
    op.create_index("ix_strategy_drafts_market", "strategy_drafts", ["market"])
    op.create_index("ix_strategy_drafts_state", "strategy_drafts", ["state"])

    op.create_table(
        "strategy_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("draft_id", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["draft_id"], ["strategy_drafts.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_strategy_messages_draft_id", "strategy_messages", ["draft_id"])


def downgrade() -> None:
    op.drop_index("ix_strategy_messages_draft_id", table_name="strategy_messages")
    op.drop_table("strategy_messages")
    op.drop_index("ix_strategy_drafts_state", table_name="strategy_drafts")
    op.drop_index("ix_strategy_drafts_market", table_name="strategy_drafts")
    op.drop_index("ix_strategy_drafts_owner", table_name="strategy_drafts")
    op.drop_table("strategy_drafts")
