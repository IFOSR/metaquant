"""Tests for paper account persistence and ledger aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.paper.contracts import PaperAccount, PaperAccountState
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


def _create(repository: SqlAlchemyPaperRepository) -> PaperAccount:
    return repository.create_account(
        owner="tester-1",
        draft_id="sd_1",
        artifact_address="sha256:" + "a" * 64,
        content_hash="sha256:" + "b" * 64,
        market="CN_A",
        instrument_ids=("600000.SH",),
        frequency="1d",
        initial_cash=Decimal("1000000"),
    )


def test_create_get_list_account() -> None:
    repository = make_repository()
    account = _create(repository)
    fetched = repository.get_account(account.id)
    assert fetched is not None
    assert fetched.state is PaperAccountState.ACTIVE
    assert repository.list_accounts(owner="tester-1")[0].id == account.id
    assert repository.list_accounts(owner="nobody") == []


def test_update_state() -> None:
    repository = make_repository()
    account = _create(repository)
    updated = repository.update_state(account.id, PaperAccountState.CLOSED)
    assert updated.state is PaperAccountState.CLOSED


def test_order_idempotency() -> None:
    repository = make_repository()
    account = _create(repository)
    first = repository.record_order(
        account_id=account.id,
        idempotency_key="day1-1",
        instrument_id="600000.SSE",
        side="BUY",
        quantity=100,
        order_clock="T_PLUS_1_OPEN",
        status="PENDING",
    )
    second = repository.record_order(
        account_id=account.id,
        idempotency_key="day1-1",
        instrument_id="600000.SSE",
        side="BUY",
        quantity=100,
        order_clock="T_PLUS_1_OPEN",
        status="PENDING",
    )
    assert first == second
    assert len(repository.list_orders(account.id)) == 1


def test_fill_updates_order_and_ledger() -> None:
    repository = make_repository()
    account = _create(repository)
    order_id = repository.record_order(
        account_id=account.id,
        idempotency_key="day1-1",
        instrument_id="600000.SSE",
        side="BUY",
        quantity=200,
        order_clock="T_PLUS_1_OPEN",
        status="PENDING",
    )
    ts = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
    repository.record_fill(
        order_id=order_id,
        account_id=account.id,
        trade_ts=ts,
        price=Decimal("10.00"),
        quantity=100,
        fee=Decimal("5.01"),
    )
    repository.record_fill(
        order_id=order_id,
        account_id=account.id,
        trade_ts=ts,
        price=Decimal("11.00"),
        quantity=100,
        fee=Decimal("5.02"),
    )
    orders = repository.list_orders(account.id)
    assert orders[0]["status"] == "FILLED"
    assert orders[0]["filled_qty"] == 200
    assert orders[0]["avg_px"] == pytest.approx(10.5)
    fills = repository.list_fills(account.id)
    assert [f["fee"] for f in fills] == [5.01, 5.02]


def test_positions_and_equity_upsert() -> None:
    repository = make_repository()
    account = _create(repository)
    repository.upsert_position(
        account_id=account.id,
        instrument_id="600000.SSE",
        quantity=100,
        avg_px=Decimal("10.00"),
    )
    repository.upsert_position(
        account_id=account.id,
        instrument_id="600000.SSE",
        quantity=50,
        avg_px=Decimal("10.50"),
    )
    positions = repository.list_positions(account.id)
    assert positions == [
        {
            "instrument_id": "600000.SSE",
            "quantity": 50,
            "avg_px": 10.5,
            "updated_at": positions[0]["updated_at"],
        }
    ]
    repository.record_equity(
        account_id=account.id,
        trade_date="2026-08-21",
        equity=Decimal("1000100"),
        cash=Decimal("900000"),
    )
    repository.record_equity(
        account_id=account.id,
        trade_date="2026-08-21",
        equity=Decimal("1000200"),
        cash=Decimal("900000"),
        margin_used=Decimal("100"),
        drawdown=Decimal("0.01"),
    )
    equity = repository.list_equity(account.id)
    assert len(equity) == 1
    assert equity[0]["equity"] == 1000200.0
    assert equity[0]["drawdown"] == 0.01
