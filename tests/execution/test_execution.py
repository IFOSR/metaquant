from __future__ import annotations

from decimal import Decimal

from quant_platform.execution.runtime import shadow_rebalance
from quant_platform.execution.safety import (
    SafetyLimits,
    check_order_safety,
    reconcile,
)
from quant_platform.markets.cn_a import OrderSide


def limits(
    notional_cap: str = "100000",
    kill_switch: bool = False,
    max_order_quantity: int | None = None,
) -> SafetyLimits:
    return SafetyLimits(
        notional_cap=Decimal(notional_cap),
        kill_switch=kill_switch,
        max_order_quantity=max_order_quantity,
    )


def test_order_within_limits_is_allowed() -> None:
    check = check_order_safety(
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("10"),
        limits=limits(),
    )

    assert check.allowed
    assert check.reason == "allowed"


def test_kill_switch_blocks_everything() -> None:
    check = check_order_safety(
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("10"),
        limits=limits(kill_switch=True),
    )

    assert not check.allowed
    assert check.reason == "kill_switch"


def test_notional_cap_blocks_large_order() -> None:
    check = check_order_safety(
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("2000"),  # 200_000 > 100_000 cap
        limits=limits(),
    )

    assert not check.allowed
    assert check.reason == "notional_cap_exceeded"


def test_max_order_quantity_blocks() -> None:
    check = check_order_safety(
        side=OrderSide.BUY,
        quantity=500,
        price=Decimal("10"),
        limits=limits(max_order_quantity=100),
    )

    assert not check.allowed
    assert check.reason == "order_quantity_exceeded"


def test_shadow_rebalance_produces_suggestions() -> None:
    target = {"A": 200, "B": 0, "C": 50}
    current = {"A": 100, "B": 100}

    suggestions = shadow_rebalance(target, current)

    by_instrument = {s.instrument_id: s for s in suggestions}
    assert by_instrument["A"].side is OrderSide.BUY
    assert by_instrument["A"].quantity == 100
    assert by_instrument["B"].side is OrderSide.SELL
    assert by_instrument["B"].quantity == 100
    assert by_instrument["C"].side is OrderSide.BUY
    assert by_instrument["C"].quantity == 50


def test_shadow_rebalance_empty_when_matched() -> None:
    target = {"A": 100, "B": 50}
    current = {"A": 100, "B": 50}

    assert shadow_rebalance(target, current) == ()


def test_reconcile_reports_differences() -> None:
    expected = {"A": 100, "B": 50}
    actual = {"A": 90, "C": 10}

    diff = reconcile(expected, actual)

    assert diff == {"A": 10, "B": 50, "C": -10}


def test_reconcile_empty_when_matched() -> None:
    assert reconcile({"A": 100}, {"A": 100}) == {}
