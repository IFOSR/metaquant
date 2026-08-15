from __future__ import annotations

from decimal import Decimal

from nautilus_trader.common.component import TestClock
from nautilus_trader.common.factories import OrderFactory
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import StrategyId, TraderId
from nautilus_trader.model.orders import Order

from quant_platform.markets.futures import CloseOffset, FeeRate, FeeSchedule
from quant_platform.markets.nt.futures_fee import close_offset_fee, offset_from_order
from quant_platform.markets.nt.instruments import equity_instrument


def schedule() -> FeeSchedule:
    return FeeSchedule(
        {
            CloseOffset.CLOSE_TODAY: FeeRate(per_lot=Decimal("100")),
            CloseOffset.CLOSE_YESTERDAY: FeeRate(per_lot=Decimal("1")),
        }
    )


def order(tags: list[str] | None = None) -> Order:
    instrument = equity_instrument(symbol="600000")
    factory = OrderFactory(
        trader_id=TraderId("TESTER-001"),
        strategy_id=StrategyId("S-001"),
        clock=TestClock(),
    )
    return factory.limit(
        instrument_id=instrument.id,
        order_side=OrderSide.BUY,
        quantity=instrument.make_qty(1),
        price=instrument.make_price("4000"),
        tags=tags,
    )


def test_close_today_fee_differs_from_yesterday() -> None:
    today = close_offset_fee(
        schedule(), CloseOffset.CLOSE_TODAY, 1, Decimal("4000"), Decimal("10")
    )
    yesterday = close_offset_fee(
        schedule(), CloseOffset.CLOSE_YESTERDAY, 1, Decimal("4000"), Decimal("10")
    )

    assert today == Decimal("100")
    assert yesterday == Decimal("1")
    assert today > yesterday


def test_offset_defaults_to_yesterday() -> None:
    assert offset_from_order(order(None)) is CloseOffset.CLOSE_YESTERDAY


def test_offset_reads_close_today_tag() -> None:
    tagged = order(["close_offset=CLOSE_TODAY"])
    assert offset_from_order(tagged) is CloseOffset.CLOSE_TODAY


def test_offset_ignores_unknown_tags() -> None:
    tagged = order(["reduce_only", "client_id=abc"])
    assert offset_from_order(tagged) is CloseOffset.CLOSE_YESTERDAY
