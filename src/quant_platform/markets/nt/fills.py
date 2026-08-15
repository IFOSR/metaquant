"""中国市场涨跌停 FillModel（G18 P3）。

涨停封板（买单无对手盘）与跌停封板（卖单无对手盘）通过返回空盘口实现，
复用 ``markets/cn_a.py`` 的涨跌停判定语义。涨跌停价由外部（数据层）传入，
不在适配层重复计算。
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.backtest.models import FillModel
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.enums import BookType, OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price
from nautilus_trader.model.orders import Order

PriceLimits = dict[InstrumentId, tuple[Decimal, Decimal]]


class PriceLimitFillModel(FillModel):  # type: ignore[misc]  # FillModel 为 C 扩展
    """涨跌停封板时返回空盘口，阻断对应方向成交。"""

    def __init__(self, price_limits: PriceLimits | None = None) -> None:
        super().__init__()
        self.price_limits: PriceLimits = price_limits or {}

    def set_price_limits(
        self, instrument_id: InstrumentId, lower: Decimal, upper: Decimal
    ) -> None:
        if not lower < upper:
            raise ValueError("lower must be below upper")
        self.price_limits[instrument_id] = (lower, upper)

    def get_orderbook_for_fill_simulation(
        self,
        instrument: Instrument,
        order: Order,
        best_bid: Price,
        best_ask: Price,
    ) -> OrderBook | None:
        limits = self.price_limits.get(instrument.id)
        if limits is not None:
            lower, upper = limits
            if order.side == OrderSide.BUY and best_ask >= instrument.make_price(upper):
                return OrderBook(instrument.id, BookType.L1_MBP)  # 涨停封板
            if order.side == OrderSide.SELL and best_bid <= instrument.make_price(
                lower
            ):
                return OrderBook(instrument.id, BookType.L1_MBP)  # 跌停封板
        return super().get_orderbook_for_fill_simulation(
            instrument, order, best_bid, best_ask
        )
