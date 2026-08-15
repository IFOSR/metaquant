from __future__ import annotations

from decimal import Decimal

from nautilus_trader.common.component import TestClock
from nautilus_trader.common.factories import OrderFactory
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import StrategyId, TraderId
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.orders import Order

from quant_platform.markets.nt.fills import PriceLimitFillModel
from quant_platform.markets.nt.instruments import equity_instrument


def _order(instrument: Equity, side: OrderSide, price: str) -> Order:
    factory = OrderFactory(
        trader_id=TraderId("TESTER-001"),
        strategy_id=StrategyId("S-001"),
        clock=TestClock(),
    )
    return factory.limit(
        instrument_id=instrument.id,
        order_side=side,
        quantity=instrument.make_qty(100),
        price=instrument.make_price(price),
    )


def test_buy_blocked_at_upper_limit() -> None:
    instrument = equity_instrument(symbol="600000")
    model = PriceLimitFillModel()
    model.set_price_limits(instrument.id, Decimal("9.0"), Decimal("11.0"))

    order = _order(instrument, OrderSide.BUY, "11.0")
    best_bid = instrument.make_price(10.9)
    best_ask = instrument.make_price(11.0)

    book = model.get_orderbook_for_fill_simulation(
        instrument, order, best_bid, best_ask
    )

    # 涨停封板：空盘口（无对手盘）
    assert book is not None
    assert len(book.bids()) == 0
    assert len(book.asks()) == 0


def test_sell_blocked_at_lower_limit() -> None:
    instrument = equity_instrument(symbol="600000")
    model = PriceLimitFillModel()
    model.set_price_limits(instrument.id, Decimal("9.0"), Decimal("11.0"))

    order = _order(instrument, OrderSide.SELL, "9.0")
    best_bid = instrument.make_price(9.0)
    best_ask = instrument.make_price(9.1)

    book = model.get_orderbook_for_fill_simulation(
        instrument, order, best_bid, best_ask
    )

    assert book is not None
    assert len(book.bids()) == 0
    assert len(book.asks()) == 0


def test_buy_within_limits_uses_default_book() -> None:
    instrument = equity_instrument(symbol="600000")
    model = PriceLimitFillModel()
    model.set_price_limits(instrument.id, Decimal("9.0"), Decimal("11.0"))

    order = _order(instrument, OrderSide.BUY, "10.0")
    best_bid = instrument.make_price(9.9)
    best_ask = instrument.make_price(10.1)

    book = model.get_orderbook_for_fill_simulation(
        instrument, order, best_bid, best_ask
    )

    # 未触及涨跌停：走默认（None = 真实盘口撮合）
    assert book is None
