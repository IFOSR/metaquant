from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from quant_platform.backtest.ledger import Fill, Ledger
from quant_platform.markets.cn_a import OrderSide


def at(day: int, hour: int = 9, minute: int = 35) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=UTC)


def buy(
    instrument: str, quantity: int, price: str, cost: str = "0", day: int = 2
) -> Fill:
    return Fill(
        fill_id=f"fill-{instrument}-{day}",
        order_id=f"order-{instrument}-{day}",
        instrument_id=instrument,
        side=OrderSide.BUY,
        quantity=quantity,
        price=Decimal(price),
        cost=Decimal(cost),
        fill_time=at(day),
        trade_date=date(2026, 8, day),
    )


def sell(
    instrument: str, quantity: int, price: str, cost: str = "0", day: int = 3
) -> Fill:
    return Fill(
        fill_id=f"fill-{instrument}-{day}",
        order_id=f"order-{instrument}-{day}",
        instrument_id=instrument,
        side=OrderSide.SELL,
        quantity=quantity,
        price=Decimal(price),
        cost=Decimal(cost),
        fill_time=at(day),
        trade_date=date(2026, 8, day),
    )


def test_buy_updates_cash_and_position() -> None:
    ledger = Ledger(cash=Decimal("100000"), positions=(), fills=())

    new = ledger.apply_fill(buy("A", 100, "10", "5"))

    assert new.cash == Decimal("100000") - Decimal("1000") - Decimal("5")
    position = new.position("A")
    assert position is not None
    assert position.quantity == 100
    assert len(new.fills) == 1


def test_sell_updates_cash_and_position() -> None:
    ledger = Ledger(cash=Decimal("100000"), positions=(), fills=())
    ledger = ledger.apply_fill(buy("A", 100, "10"))

    new = ledger.apply_fill(sell("A", 100, "12", "3"))

    assert new.position("A") is None
    assert new.cash == Decimal("100000") - Decimal("1000") + Decimal("1200") - Decimal(
        "3"
    )


def test_insufficient_cash_rejected() -> None:
    ledger = Ledger(cash=Decimal("100"), positions=(), fills=())

    with pytest.raises(ValueError):
        ledger.apply_fill(buy("A", 100, "10"))


def test_insufficient_position_rejected() -> None:
    ledger = Ledger(cash=Decimal("100000"), positions=(), fills=())

    with pytest.raises(ValueError):
        ledger.apply_fill(sell("A", 100, "10"))


def test_nav_sums_cash_and_positions() -> None:
    ledger = Ledger(cash=Decimal("1000"), positions=(), fills=())
    ledger = ledger.apply_fill(buy("A", 100, "10"))

    nav = ledger.nav({"A": Decimal("11")})

    assert nav == Decimal("1000") - Decimal("1000") + Decimal("1100")


def test_nav_requires_price_for_every_position() -> None:
    ledger = Ledger(cash=Decimal("1000"), positions=(), fills=())
    ledger = ledger.apply_fill(buy("A", 100, "10"))

    with pytest.raises(ValueError):
        ledger.nav({})


def test_mark_to_market_appends_history() -> None:
    ledger = Ledger(cash=Decimal("1000"), positions=(), fills=())
    ledger = ledger.apply_fill(buy("A", 100, "10"))

    marked = ledger.mark_to_market({"A": Decimal("11")}, date(2026, 8, 2))

    assert marked.nav_history == ((date(2026, 8, 2), Decimal("1100")),)


def test_position_average_cost_on_multiple_buys() -> None:
    ledger = Ledger(cash=Decimal("100000"), positions=(), fills=())
    ledger = ledger.apply_fill(buy("A", 100, "10"))
    ledger = ledger.apply_fill(buy("A", 100, "20", day=3))

    position = ledger.position("A")
    assert position is not None
    assert position.quantity == 200
    assert position.average_cost == Decimal("15")


def test_ledger_payload_is_round_trippable() -> None:
    ledger = Ledger(cash=Decimal("100000"), positions=(), fills=())
    ledger = ledger.apply_fill(buy("A", 100, "10"))

    payload = ledger.payload()

    assert payload["schema_version"] == "backtest-ledger/v1"
    assert payload["cash"] == "99000"
    assert payload["positions"] == [
        {"instrument_id": "A", "quantity": 100, "average_cost": "10"}
    ]
