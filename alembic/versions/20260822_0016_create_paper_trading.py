"""Create paper trading tables.

Revision ID: 20260822_0016
Revises: 20260822_0015
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0016"
down_revision: str | None = "20260822_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("draft_id", sa.String(64), nullable=False),
        sa.Column("artifact_address", sa.String(80), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("instrument_ids", sa.JSON(), nullable=False),
        sa.Column("frequency", sa.String(16), nullable=False),
        sa.Column("initial_cash", sa.Numeric(20, 2), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_paper_accounts_owner", "paper_accounts", ["owner"])
    op.create_index("ix_paper_accounts_draft_id", "paper_accounts", ["draft_id"])
    op.create_index("ix_paper_accounts_state", "paper_accounts", ["state"])

    op.create_table(
        "paper_orders",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("instrument_id", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("order_clock", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reject_reason", sa.String(255), nullable=True),
        sa.Column("filled_qty", sa.Integer(), nullable=False),
        sa.Column("avg_px", sa.Numeric(20, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "account_id", "idempotency_key", name="uq_paper_order_idem"
        ),
    )
    op.create_index("ix_paper_orders_account_id", "paper_orders", ["account_id"])
    op.create_index("ix_paper_orders_status", "paper_orders", ["status"])

    op.create_table(
        "paper_fills",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "order_id",
            sa.String(64),
            sa.ForeignKey("paper_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trade_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(20, 6), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("fee", sa.Numeric(20, 4), nullable=False),
        sa.Column("notional", sa.Numeric(24, 4), nullable=False),
    )
    op.create_index("ix_paper_fills_order_id", "paper_fills", ["order_id"])
    op.create_index("ix_paper_fills_account_id", "paper_fills", ["account_id"])

    op.create_table(
        "paper_positions",
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("instrument_id", sa.String(64), primary_key=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("avg_px", sa.Numeric(20, 6), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "paper_equity",
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("trade_date", sa.String(10), primary_key=True),
        sa.Column("equity", sa.Numeric(24, 4), nullable=False),
        sa.Column("cash", sa.Numeric(24, 4), nullable=False),
        sa.Column("margin_used", sa.Numeric(24, 4), nullable=False),
        sa.Column("drawdown", sa.Numeric(12, 8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("paper_equity")
    op.drop_table("paper_positions")
    op.drop_index("ix_paper_fills_account_id", table_name="paper_fills")
    op.drop_index("ix_paper_fills_order_id", table_name="paper_fills")
    op.drop_table("paper_fills")
    op.drop_index("ix_paper_orders_status", table_name="paper_orders")
    op.drop_index("ix_paper_orders_account_id", table_name="paper_orders")
    op.drop_table("paper_orders")
    op.drop_index("ix_paper_accounts_state", table_name="paper_accounts")
    op.drop_index("ix_paper_accounts_draft_id", table_name="paper_accounts")
    op.drop_index("ix_paper_accounts_owner", table_name="paper_accounts")
    op.drop_table("paper_accounts")
