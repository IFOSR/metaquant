from __future__ import annotations

from decimal import Decimal

from nautilus_trader.common.component import TestClock
from nautilus_trader.common.factories import OrderFactory
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import StrategyId, TraderId
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.orders import Order

from quant_platform.markets.nt.fees import AShareFeeModel
from quant_platform.markets.nt.instruments import equity_instrument


def _buy_order() -> tuple[Order, Equity]:
    instrument = equity_instrument(symbol="600000")
    factory = OrderFactory(
        trader_id=TraderId("TESTER-001"),
        strategy_id=StrategyId("S-001"),
        clock=TestClock(),
    )
    return factory.limit(
        instrument_id=instrument.id,
        order_side=OrderSide.BUY,
        quantity=instrument.make_qty(1000),
        price=instrument.make_price(10.0),
    ), instrument


def test_buy_commission_minimum() -> None:
    order, instrument = _buy_order()
    model = AShareFeeModel()

    # 1000 股 × 10 元 = 10000 元；佣金 10000 × 0.0003 = 3 元 < 最低 5 元
    commission = model.get_commission(order, order.quantity, order.price, instrument)

    # 佣金 5（最低）+ 过户费 10000 × 0.00001 = 0.1；无印花税
    assert commission.as_decimal() == Decimal("5.10")


def test_sell_commission_includes_stamp_duty() -> None:
    instrument = equity_instrument(symbol="600000")
    factory = OrderFactory(
        trader_id=TraderId("TESTER-001"),
        strategy_id=StrategyId("S-001"),
        clock=TestClock(),
    )
    order = factory.limit(
        instrument_id=instrument.id,
        order_side=OrderSide.SELL,
        quantity=instrument.make_qty(1000),
        price=instrument.make_price(10.0),
    )
    model = AShareFeeModel()

    commission = model.get_commission(order, order.quantity, order.price, instrument)

    # 佣金 5 + 印花税 10000 × 0.0005 = 5 + 过户费 0.1 = 10.10
    assert commission.as_decimal() == Decimal("10.10")
