"""期货逐日盯市结算组件 (G18-P3)。

NautilusTrader 内置的只有到期最终结算（``settlement_prices`` +
``InstrumentClose``）和永续资金费结算，没有中国式逐日盯市（按结算价每日
现金划转）。本组件复用 ``markets/futures.py`` 的 ``settle()``（唯一事实源），
把多合约的每日盯市盈亏汇总为现金划转金额，供适配层在每日结算价到达时
调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quant_platform.markets.futures import SettlementInput, settle


@dataclass(frozen=True, slots=True)
class SettlementLeg:
    instrument_id: str
    previous_quantity: int
    previous_settlement: Decimal
    opened_quantity: int
    opened_price: Decimal
    settlement_price: Decimal

    def __post_init__(self) -> None:
        if not self.instrument_id or self.instrument_id.strip() != self.instrument_id:
            raise ValueError("instrument_id must be a non-empty normalized identifier")


@dataclass(frozen=True, slots=True)
class DailySettlement:
    mark_to_market: Decimal
    ending_quantities: dict[str, int]

    def payload(self) -> dict[str, object]:
        return {
            "mark_to_market": str(self.mark_to_market),
            "ending_quantities": {
                instrument: quantity
                for instrument, quantity in self.ending_quantities.items()
            },
        }


def settle_daily(
    legs: tuple[SettlementLeg, ...],
    *,
    multiplier: Decimal,
    fees: Decimal = Decimal("0"),
) -> DailySettlement:
    """多合约逐日盯市结算，返回总盯市盈亏（划转现金）。"""
    total = Decimal("0")
    ending: dict[str, int] = {}
    for leg in legs:
        result = settle(
            SettlementInput(
                previous_quantity=leg.previous_quantity,
                previous_settlement=leg.previous_settlement,
                opened_quantity=leg.opened_quantity,
                opened_price=leg.opened_price,
                settlement_price=leg.settlement_price,
                multiplier=multiplier,
                fees=Decimal("0"),
            )
        )
        total += result.mark_to_market
        ending[leg.instrument_id] = result.ending_quantity
    return DailySettlement(
        mark_to_market=total - fees,
        ending_quantities=ending,
    )
