"""期货平今平昨费率适配 (G18-P3)。

把 ``markets/futures.py`` 的 ``FeeSchedule``（唯一事实源）桥接到
NautilusTrader FeeModel。平今/平昨的区分通过订单的 ``tags`` 标记
``close_offset=CLOSE_TODAY`` / ``close_offset=CLOSE_YESTERDAY``（策略层在
生成平仓单时写入），默认按平昨计费。
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.backtest.models import FeeModel
from nautilus_trader.model.currencies import CNY
from nautilus_trader.model.objects import Money
from nautilus_trader.model.orders import Order

from quant_platform.markets.futures import CloseOffset, FeeSchedule


def close_offset_fee(
    schedule: FeeSchedule,
    offset: CloseOffset,
    quantity: int,
    price: Decimal,
    multiplier: Decimal,
) -> Decimal:
    """按平今/平昨选择费率计算平仓费用。"""
    return schedule.calculate(offset, quantity, price, multiplier)


def offset_from_order(order: Order) -> CloseOffset:
    """从订单 tags 读取平今/平昨标记，默认平昨。"""
    for tag in order.tags or ():
        if tag.startswith("close_offset="):
            value = tag.split("=", 1)[1]
            if value == CloseOffset.CLOSE_TODAY.value:
                return CloseOffset.CLOSE_TODAY
    return CloseOffset.CLOSE_YESTERDAY


class FuturesFeeModel(FeeModel):  # type: ignore[misc]  # FeeModel 为 C 扩展
    """期货平仓费用：按平今/平昨分桶，复用 FeeSchedule。"""

    def __init__(self, schedule: FeeSchedule, multiplier: Decimal) -> None:
        super().__init__()
        self.schedule = schedule
        self.multiplier = multiplier

    def get_commission(
        self,
        order: Order,
        fill: object,
        fill_px: float,
        multiplier: Decimal,
    ) -> Money:
        offset = offset_from_order(order)
        fee = close_offset_fee(
            self.schedule,
            offset,
            int(order.quantity.as_double()),
            Decimal(str(fill_px)),
            self.multiplier,
        )
        return Money(fee, CNY)
