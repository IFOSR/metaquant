from __future__ import annotations

from decimal import Decimal

import pytest

from quant_platform.markets.futures import MarginSchedule
from quant_platform.markets.nt.liquidation import check_margin_call


def schedule() -> MarginSchedule:
    return MarginSchedule(
        exchange_rate=Decimal("0.08"),
        broker_rate=Decimal("0.10"),
    )


def test_margin_call_triggered_below_maintenance() -> None:
    # 初始保证金 = 4000 * 10 * 1 * 0.10 = 4000；维持 = 4000 * 0.8 = 3200
    result = check_margin_call(
        equity=Decimal("3000"),
        settlement_price=Decimal("4000"),
        multiplier=Decimal("10"),
        quantity=1,
        margin_schedule=schedule(),
        maintenance_ratio=Decimal("0.8"),
    )

    assert result.liquidated
    assert result.reason == "margin_call"


def test_no_margin_call_above_maintenance() -> None:
    result = check_margin_call(
        equity=Decimal("5000"),
        settlement_price=Decimal("4000"),
        multiplier=Decimal("10"),
        quantity=1,
        margin_schedule=schedule(),
        maintenance_ratio=Decimal("0.8"),
    )

    assert not result.liquidated


def test_zero_quantity_no_liquidation() -> None:
    result = check_margin_call(
        equity=Decimal("0"),
        settlement_price=Decimal("4000"),
        multiplier=Decimal("10"),
        quantity=0,
        margin_schedule=schedule(),
        maintenance_ratio=Decimal("0.8"),
    )

    assert not result.liquidated


def test_invalid_maintenance_ratio_rejected() -> None:
    with pytest.raises(ValueError, match="maintenance_ratio"):
        check_margin_call(
            equity=Decimal("3000"),
            settlement_price=Decimal("4000"),
            multiplier=Decimal("10"),
            quantity=1,
            margin_schedule=schedule(),
            maintenance_ratio=Decimal("1.5"),
        )
