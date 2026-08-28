"""Venue 装配 = 市场规则落点（对齐 NT ``add_venue`` 交互）。

NT 的交互逻辑里，撮合/费用/滑点/延迟/价格保护/账户类型全部是
``BacktestEngine.add_venue()`` 的参数，而不是散落在策略或调用方。这里把
这些执行假设显式建模成 ``VenueSpec``，回测与仿真（paper）共用同一份，
保证撮合假设同源。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from nautilus_trader.backtest.models import FeeModel, FillModel, LatencyModel

from quant_platform.markets.futures import CloseOffset, FeeRate, FeeSchedule
from quant_platform.markets.nt.fees import AShareFeeModel
from quant_platform.markets.nt.fills import PriceLimitFillModel
from quant_platform.markets.nt.futures_fee import FuturesFeeModel

# 期货默认演示费率（开仓按平昨、未打 tag 的平仓单也按平昨计，与 G18 一致）。
DEFAULT_FUTURES_FEE_SCHEDULE = FeeSchedule(
    {
        CloseOffset.CLOSE_TODAY: FeeRate(per_lot=Decimal("10")),
        CloseOffset.CLOSE_YESTERDAY: FeeRate(per_lot=Decimal("2")),
    }
)

PriceLimits = dict[str, tuple[Decimal, Decimal]]


@dataclass(frozen=True, slots=True)
class VenueSpec:
    """一次回测/仿真的全部执行假设（对应 NT ``add_venue`` 的参数）。

    报告披露时以 ``payload()`` 携带口径声明，让「用了什么撮合/费用/延迟/种子」
    显式可审计，消除「报告不含口径」的落差。
    """

    market: str  # CN_A / CN_COMMODITY_FUTURES → account_type 派生
    fee_model: FeeModel | None = None
    fill_model: FillModel | None = None
    latency_model: LatencyModel | None = None
    random_seed: int | None = None
    price_protection_points: int | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "cost_basis": ("net_of_fees" if self.fee_model is not None else "gross"),
            "fee_model": (
                type(self.fee_model).__name__ if self.fee_model is not None else None
            ),
            "fill_model": (
                type(self.fill_model).__name__ if self.fill_model is not None else None
            ),
            "latency_model": (
                type(self.latency_model).__name__
                if self.latency_model is not None
                else None
            ),
            "random_seed": self.random_seed,
            "price_protection_points": self.price_protection_points,
        }


def venue_spec_for_market(
    market: str,
    *,
    futures_fee_schedule: FeeSchedule = DEFAULT_FUTURES_FEE_SCHEDULE,
    price_limits: PriceLimits | None = None,
) -> VenueSpec:
    """按市场派生完整 VenueSpec（费用 + 涨跌停撮合，latency/seed 可后续扩展）。"""
    if market == "CN_A":
        return VenueSpec(
            market=market,
            fee_model=AShareFeeModel(),
            fill_model=PriceLimitFillModel(price_limits or {}),
        )
    if market == "CN_COMMODITY_FUTURES":
        return VenueSpec(
            market=market,
            fee_model=FuturesFeeModel(futures_fee_schedule),
            fill_model=PriceLimitFillModel(price_limits or {}),
        )
    raise ValueError(f"unsupported market: {market}")
