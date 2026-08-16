from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from quant_platform.execution.safety import (
    KillSwitch,
    KillSwitchState,
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


def test_reconcile_reports_differences() -> None:
    expected = {"A": 100, "B": 50}
    actual = {"A": 90, "C": 10}

    diff = reconcile(expected, actual)

    assert diff == {"A": 10, "B": 50, "C": -10}


def armed_switch() -> KillSwitch:
    return KillSwitch(
        switch_id="execution-cn-a",
        state=KillSwitchState.ARMED,
        tripped_by=None,
        tripped_at=None,
        reason=None,
    )


def test_kill_switch_trip_and_reset() -> None:
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    tripped = armed_switch().trip("risk-officer-1", "data anomaly", now)

    assert tripped.state is KillSwitchState.TRIPPED
    assert tripped.blocks()
    assert tripped.tripped_by == "risk-officer-1"

    reset = tripped.reset("risk-officer-2", now)
    assert reset.state is KillSwitchState.ARMED
    assert not reset.blocks()


def test_kill_switch_requires_reason_to_trip() -> None:
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="reason"):
        armed_switch().trip("risk-officer-1", "", now)


def test_kill_switch_is_content_addressed() -> None:
    assert armed_switch().content_hash() == armed_switch().content_hash()


def test_tripped_kill_switch_requires_audit_fields() -> None:
    with pytest.raises(ValueError):
        KillSwitch(
            switch_id="execution-cn-a",
            state=KillSwitchState.TRIPPED,
            tripped_by=None,
            tripped_at=None,
            reason=None,
        )


def test_reconcile_empty_when_matched() -> None:
    assert reconcile({"A": 100}, {"A": 100}) == {}
