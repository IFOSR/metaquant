"""Tests for ledger reconciliation and mark-to-market equity."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.paper.ledger import (
    fill_key,
    mark_to_market,
    reconcile_fills,
)
from quant_platform.paper.repository import SqlAlchemyPaperRepository
from quant_platform.research.models import Base


def make_repository() -> SqlAlchemyPaperRepository:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return SqlAlchemyPaperRepository(engine)


def _fill_row(
    client_order_id: str,
    *,
    side: str = "BUY",
    qty: int = 100,
    px: str = "10.00",
    commissions: tuple[str, ...] = ("5.01 CNY",),
) -> dict[str, object]:
    return {
        "client_order_id": client_order_id,
        "instrument_id": "600000.SSE",
        "side": side,
        "quantity": str(qty),
        "filled_qty": str(qty),
        "avg_px": px,
        "commissions": commissions,
        "ts_last": datetime(2026, 8, 21, 1, 0, tzinfo=UTC),
    }


def test_reconcile_is_idempotent() -> None:
    repository = make_repository()
    account_id = repository.create_account(
        owner="t",
        draft_id="sd_1",
        artifact_address="sha256:" + "a" * 64,
        content_hash="sha256:" + "b" * 64,
        market="CN_A",
        instrument_ids=("600000.SH",),
        frequency="1d",
        initial_cash=Decimal("1000000"),
    ).id
    rows = [_fill_row("O-1"), _fill_row("O-2", side="SELL", px="10.50")]
    first = reconcile_fills(
        repository=repository, account_id=account_id, fills_report=rows
    )
    assert first == 2
    second = reconcile_fills(
        repository=repository, account_id=account_id, fills_report=rows
    )
    assert second == 0
    orders = repository.list_orders(account_id)
    assert len(orders) == 2
    fills = repository.list_fills(account_id)
    assert len(fills) == 2
    assert fills[0]["fee"] == 5.01


def test_fill_key_is_deterministic() -> None:
    a = fill_key("O-1", "2026-08-21T01:00:00+00:00", "100", "10.0")
    b = fill_key("O-1", "2026-08-21T01:00:00+00:00", "100", "10.0")
    c = fill_key("O-1", "2026-08-21T01:00:00+00:00", "200", "10.0")
    assert a == b
    assert a != c
    assert a.startswith("pfk_")


def test_mark_to_market_cash_account() -> None:
    snapshot = mark_to_market(
        initial_cash=1_000_000.0,
        realized_pnl=0.0,
        positions={"600000.SH": 100},
        marks={"600000.SH": 10.0},
        multipliers={"600000.SH": 1},
        margin_account=False,
    )
    # 100 股 × 10 元持仓，浮盈 0：equity 不变，cash = equity - 持仓市值。
    assert snapshot.equity == 1_000_000.0
    assert snapshot.cash == 1_000_000.0 - 1_000.0
    assert snapshot.margin_used == 0.0


def test_mark_to_market_margin_account() -> None:
    snapshot = mark_to_market(
        initial_cash=1_000_000.0,
        realized_pnl=500.0,
        positions={"RB2610.SHF": 2},
        marks={"RB2610.SHF": 4000.0},
        entries={"RB2610.SHF": 3800.0},
        multipliers={"RB2610.SHF": 10},
        margin_account=True,
    )
    # 浮盈 = 2 手 × (4000 − 3800) × 10 = 4,000；保证金占用按最新价计。
    assert snapshot.equity == 1_000_000.0 + 500.0 + 4_000.0
    assert snapshot.margin_used == 80_000.0
    assert snapshot.cash == snapshot.equity - 80_000.0


def test_drawdown_when_underwater() -> None:
    snapshot = mark_to_market(
        initial_cash=1_000_000.0,
        realized_pnl=-100_000.0,
        positions={},
        marks={},
        margin_account=False,
    )
    assert snapshot.equity == 900_000.0
    assert snapshot.drawdown == 0.1
