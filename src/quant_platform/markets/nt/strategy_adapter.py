"""NautilusTrader 策略适配层 (G18-P5)。

把研究内核的 ``StrategySpec``（因子权重 + 风险限制）编译成目标仓位计算与
调仓订单生成。回测与 paper/live 共用同一份决策逻辑，消除回测/实盘偏差。
组合复用 ``portfolio`` 的 MVP 组合与约束。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quant_platform.execution.contracts import OrderInstruction
from quant_platform.markets.cn_a import OrderSide
from quant_platform.portfolio.combination import (
    CombinationSpec,
    FactorSignal,
    mvp_combine,
)
from quant_platform.strategy import StrategySpec


@dataclass(frozen=True, slots=True)
class RebalancePlan:
    target_weights: dict[str, float]
    orders: tuple[OrderInstruction, ...]

    def payload(self) -> dict[str, object]:
        return {
            "target_weights": {
                instrument: weight for instrument, weight in self.target_weights.items()
            },
            "orders": [order.payload() for order in self.orders],
        }


class StrategyAdapter:
    """把 StrategySpec 编译成目标仓位与调仓订单。"""

    def __init__(self, spec: StrategySpec) -> None:
        self.spec = spec

    def compute_target_weights(
        self, signals: tuple[FactorSignal, ...]
    ) -> dict[str, float]:
        """根据因子 IC 信号 + spec 约束，计算归一化目标权重。"""
        if not signals:
            return {}
        combined = mvp_combine(
            signals,
            CombinationSpec(
                spec_id=self.spec.strategy_id,
                max_weight=float(self.spec.risk_limits.max_single_weight),
            ),
        )
        return combined.weights_map()

    def plan(
        self,
        *,
        signals: tuple[FactorSignal, ...],
        instrument_ids: tuple[str, ...],
        current_weights: dict[str, float],
        price: Decimal,
        lot_size: int = 100,
    ) -> RebalancePlan:
        """生成调仓计划：目标权重 + 目标/当前仓位差对应的订单指令。"""
        target = self.compute_target_weights(signals)
        orders: list[OrderInstruction] = []
        for instrument_id in instrument_ids:
            target_weight = target.get(instrument_id, 0.0)
            current_weight = current_weights.get(instrument_id, 0.0)
            delta = target_weight - current_weight
            if abs(delta) < 1e-9:
                continue
            quantity = int(abs(delta) * float(price) // 1 // lot_size * lot_size)
            if quantity <= 0:
                continue
            orders.append(
                OrderInstruction(
                    order_id=f"rebalance-{instrument_id}",
                    instrument_id=instrument_id,
                    side=OrderSide.BUY if delta > 0 else OrderSide.SELL,
                    quantity=quantity,
                    idempotency_key=f"rebalance-{instrument_id}",
                )
            )
        return RebalancePlan(target_weights=target, orders=tuple(orders))
