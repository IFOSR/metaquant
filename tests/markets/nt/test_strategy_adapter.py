from __future__ import annotations

from decimal import Decimal

from quant_platform.markets.cn_a import OrderSide
from quant_platform.markets.nt.strategy_adapter import StrategyAdapter
from quant_platform.portfolio.combination import FactorSignal
from quant_platform.strategy import RiskLimits, StrategySpec
from quant_platform.validation.alpha_pool import FactorDirection


def spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="strategy://cn-a-momentum/v1",
        market="CN_A",
        universe_ref="universe://csi300/v1",
        frequency="1d",
        factor_weights=(
            ("a" * 64, Decimal("0.6")),
            ("b" * 64, Decimal("0.4")),
        ),
        leverage=Decimal("1"),
        risk_limits=RiskLimits(
            max_single_weight=Decimal("0.6"),
            max_holdings=5,
            turnover_budget=Decimal("0.3"),
        ),
        cost_model_ref="cost://cn-a-default/v1",
        validation_policy_ref="policy://cn-a-daily-factor/v1",
    )


def signals() -> tuple[FactorSignal, ...]:
    return (
        FactorSignal(
            factor_ir_hash="a" * 64,
            train_ic=0.05,
            ic_vol=0.08,
            direction=FactorDirection.LONG_SHORT,
        ),
        FactorSignal(
            factor_ir_hash="b" * 64,
            train_ic=0.03,
            ic_vol=0.06,
            direction=FactorDirection.LONG_SHORT,
        ),
    )


def test_compute_target_weights_normalizes() -> None:
    adapter = StrategyAdapter(spec())

    weights = adapter.compute_target_weights(signals())

    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert len(weights) == 2


def test_empty_signals_yield_no_weights() -> None:
    adapter = StrategyAdapter(spec())

    assert adapter.compute_target_weights(()) == {}


def test_plan_generates_rebalance_orders() -> None:
    adapter = StrategyAdapter(spec())

    plan = adapter.plan(
        signals=signals(),
        instrument_ids=("a" * 64, "b" * 64),
        current_weights={},
        price=Decimal("1000"),
        lot_size=100,
    )

    assert plan.orders
    assert all(order.side in (OrderSide.BUY, OrderSide.SELL) for order in plan.orders)


def test_plan_no_orders_when_aligned() -> None:
    adapter = StrategyAdapter(spec())
    target = adapter.compute_target_weights(signals())

    plan = adapter.plan(
        signals=signals(),
        instrument_ids=tuple(target.keys()),
        current_weights=target,
        price=Decimal("1000"),
    )

    assert plan.orders == ()
