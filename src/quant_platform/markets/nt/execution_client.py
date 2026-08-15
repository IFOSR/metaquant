"""NautilusTrader 订单网关 (G18-P4)。

把研究内核的 ``OrderInstruction`` 桥接到 NautilusTrader 订单，并在提交前
执行安全校验（kill switch、notional cap、单笔上限），复用
``execution/safety.py`` 的纯函数。paper 模式记录订单不实发；live 模式
预留 ExecutionClient 提交点。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from nautilus_trader.common.component import TestClock
from nautilus_trader.common.factories import OrderFactory
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import StrategyId, TraderId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import Order

from quant_platform.execution.contracts import OrderInstruction
from quant_platform.execution.safety import (
    KillSwitch,
    SafetyLimits,
    check_order_safety,
)
from quant_platform.markets.cn_a import OrderSide as InstructionSide


@dataclass(frozen=True, slots=True)
class SubmitResult:
    accepted: bool
    reason: str | None = None
    order: Order | None = None

    @classmethod
    def reject(cls, reason: str) -> SubmitResult:
        return cls(accepted=False, reason=reason)

    @classmethod
    def accept(cls, order: Order) -> SubmitResult:
        return cls(accepted=True, order=order)


def _to_nautilus_side(side: InstructionSide) -> OrderSide:
    return OrderSide.BUY if side is InstructionSide.BUY else OrderSide.SELL


class NautilusOrderGateway:
    """把 OrderInstruction 桥接到 NautilusTrader 订单并执行安全校验。"""

    def __init__(
        self,
        *,
        limits: SafetyLimits,
        kill_switch: KillSwitch,
        clock: object | None = None,
    ) -> None:
        self.limits = limits
        self.kill_switch = kill_switch
        self._clock = clock or TestClock()
        self._factory = OrderFactory(
            trader_id=TraderId("QUANT-001"),
            strategy_id=StrategyId("QUANT-STRAT-001"),
            clock=self._clock,
        )

    def submit(
        self,
        instruction: OrderInstruction,
        instrument: Instrument,
        *,
        price: Decimal,
        limit_price: Decimal | None = None,
    ) -> SubmitResult:
        # 1. Kill switch 全局阻断。
        if self.kill_switch.blocks():
            return SubmitResult.reject("kill_switch")
        # 2. notional cap / max order quantity（用参考价估算）。
        check = check_order_safety(
            side=instruction.side,
            quantity=instruction.quantity,
            price=price,
            limits=self.limits,
        )
        if not check.allowed:
            return SubmitResult.reject(check.reason)
        # 3. 桥接为 NautilusTrader 订单。
        side = _to_nautilus_side(instruction.side)
        if limit_price is not None:
            order = self._factory.limit(
                instrument_id=instrument.id,
                order_side=side,
                quantity=instrument.make_qty(instruction.quantity),
                price=instrument.make_price(str(limit_price)),
            )
        else:
            order = self._factory.market(
                instrument_id=instrument.id,
                order_side=side,
                quantity=instrument.make_qty(instruction.quantity),
            )
        return SubmitResult.accept(order)
