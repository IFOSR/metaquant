"""期货保证金强平 (G18-P3)。

NautilusTrader 无内置强平。本模块复用 ``markets/futures.py`` 的
``MarginSchedule``（唯一事实源），在每日盯市后检查权益是否低于维持保证金，
低于即触发强平。语义对齐原 ``futures_engine.py`` 的 ``forced_liquidation``。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quant_platform.markets.futures import MarginSchedule


@dataclass(frozen=True, slots=True)
class LiquidationResult:
    liquidated: bool
    reason: str | None = None

    def payload(self) -> dict[str, object]:
        return {"liquidated": self.liquidated, "reason": self.reason}


def check_margin_call(
    *,
    equity: Decimal,
    settlement_price: Decimal,
    multiplier: Decimal,
    quantity: int,
    margin_schedule: MarginSchedule,
    maintenance_ratio: Decimal,
) -> LiquidationResult:
    """盯市后权益低于维持保证金即触发强平。

    ``maintenance_ratio`` 是维持保证金占初始保证金的比例（通常 < 1）。
    """
    if not Decimal("0") < maintenance_ratio <= Decimal("1"):
        raise ValueError("maintenance_ratio must be within (0, 1]")
    if quantity <= 0:
        return LiquidationResult(liquidated=False)
    required = margin_schedule.required_margin(settlement_price, multiplier, quantity)
    maintenance = required * maintenance_ratio
    if equity < maintenance:
        return LiquidationResult(liquidated=True, reason="margin_call")
    return LiquidationResult(liquidated=False)
