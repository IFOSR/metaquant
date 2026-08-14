from __future__ import annotations

from decimal import Decimal

import pytest

from quant_platform.validation.attribution import (
    AttributionReport,
    CostBreakdown,
    build_attribution_report,
)

D = Decimal


def costs() -> CostBreakdown:
    return CostBreakdown(
        commission=D("120"),
        stamp_duty=D("60"),
        slippage=D("30"),
        impact=D("90"),
    )


def report(**overrides: object) -> AttributionReport:
    fields: dict[str, object] = {
        "start_nav": D("1_000_000"),
        "gross_pnl": D("100_000"),
        "cost_breakdown": costs(),
        "risk_exposures": (("momentum", 0.4), ("value", -0.1)),
        "capacity_utilization": 0.05,
        "unfillable_count": 3,
        "total_orders": 100,
    }
    fields.update(overrides)
    return build_attribution_report(**fields)  # type: ignore[arg-type]


def test_gross_and_net_return() -> None:
    result = report()

    assert result.gross_return == D("0.1")
    # costs total 300 -> net pnl 99700 -> 9.97%
    assert result.net_return == D("99700") / D("1_000_000")


def test_cost_breakdown_total() -> None:
    assert costs().total() == D("300")


def test_unfillable_ratio() -> None:
    assert report().unfillable_ratio == pytest.approx(0.03)


def test_roll_return_and_ablation_passthrough() -> None:
    result = report(
        roll_return=D("5000"),
        factor_ablation=(("momentum", 0.06), ("value", 0.02)),
    )

    assert result.roll_return == D("5000")
    assert result.factor_ablation == (("momentum", 0.06), ("value", 0.02))


def test_report_is_content_addressed() -> None:
    first = report()
    second = report()

    assert first.content_hash() == second.content_hash()


def test_rejects_nonpositive_start_nav() -> None:
    with pytest.raises(ValueError, match="start_nav"):
        report(start_nav=D("0"))


def test_rejects_unfillable_beyond_total() -> None:
    with pytest.raises(ValueError, match="unfillable"):
        report(unfillable_count=101, total_orders=100)


def test_rejects_out_of_range_capacity() -> None:
    with pytest.raises(ValueError, match="capacity"):
        report(capacity_utilization=1.5)
