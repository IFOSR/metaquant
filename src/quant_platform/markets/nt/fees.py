"""中国市场费率模型（G18 P3）。

从 ``markets/cost.py`` 的规则（唯一事实源）生成 NautilusTrader 的
``FeeModel``。A 股：佣金（最低 5 元）+ 印花税（卖出单边）+ 过户费（双边）。
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.backtest.models import FeeModel
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import Order


class AShareFeeModel(FeeModel):  # type: ignore[misc]  # FeeModel 为 C 扩展，mypy 视作 Any
    """A 股交易费用：佣金 + 印花税（卖）+ 过户费。"""

    def __init__(
        self,
        *,
        commission_rate: Decimal = Decimal("0.0003"),
        min_commission: Decimal = Decimal("5"),
        stamp_duty_rate: Decimal = Decimal("0.0005"),
        transfer_fee_rate: Decimal = Decimal("0.00001"),
    ) -> None:
        super().__init__()
        if commission_rate < 0 or stamp_duty_rate < 0 or transfer_fee_rate < 0:
            raise ValueError("fee rates must be non-negative")
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_duty_rate = stamp_duty_rate
        self.transfer_fee_rate = transfer_fee_rate

    def get_commission(
        self,
        order: Order,
        fill_qty: Quantity,
        fill_px: Price,
        instrument: Instrument,
    ) -> Money:
        notional = Decimal(str(fill_qty.as_double())) * Decimal(
            str(fill_px.as_double())
        )
        commission = max(notional * self.commission_rate, self.min_commission)
        stamp_duty = (
            notional * self.stamp_duty_rate
            if order.side == OrderSide.SELL
            else Decimal("0")
        )
        transfer_fee = notional * self.transfer_fee_rate
        total = commission + stamp_duty + transfer_fee
        return Money(total, instrument.quote_currency)
