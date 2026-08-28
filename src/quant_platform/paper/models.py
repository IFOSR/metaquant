"""SQLAlchemy models for paper trading tables.

Kept in a dedicated module (not appended to ``research/models.py``) so the
paper platform owns its schema surface.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from quant_platform.research.models import Base


class PaperAccountModel(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    draft_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    artifact_address: Mapped[str] = mapped_column(String(80), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PaperOrderModel(Base):
    __tablename__ = "paper_orders"
    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key", name="uq_paper_order_idem"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    order_clock: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reject_reason: Mapped[str | None] = mapped_column(String(255))
    filled_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_px: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PaperFillModel(Base):
    __tablename__ = "paper_fills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("paper_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trade_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    notional: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)


class PaperPositionModel(Base):
    __tablename__ = "paper_positions"

    account_id: Mapped[str] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    instrument_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_px: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PaperEquityModel(Base):
    __tablename__ = "paper_equity"

    account_id: Mapped[str] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    trade_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    equity: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    margin_used: Mapped[Decimal] = mapped_column(
        Numeric(24, 4), nullable=False, default=0
    )
    drawdown: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PaperRunStateModel(Base):
    """仿真节点逐周期写入的运行进度（供运维页展示「跑到哪一步」）。"""

    __tablename__ = "paper_run_state"

    account_id: Mapped[str] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    cycles_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bars_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_bar_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
