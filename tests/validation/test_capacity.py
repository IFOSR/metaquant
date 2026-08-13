from __future__ import annotations

import pytest

from quant_platform.validation.capacity import (
    CapacityModel,
    run_capacity,
)


def model() -> CapacityModel:
    return CapacityModel(
        market="CN_A",
        max_adv_participation=0.01,
        impact_coefficient=0.1,
        margin_rate=1.0,
        exclude_limit_up_down=True,
        exclude_suspended=True,
    )


def test_run_capacity_is_deterministic() -> None:
    adv = {"A": 1000.0, "B": 2000.0, "C": 3000.0}
    tradable = {"A": True, "B": True, "C": False}

    first = run_capacity(adv, tradable, model())
    second = run_capacity(adv, tradable, model())

    assert first == second
    assert first.content_hash() == second.content_hash()


def test_per_name_capacity_applies_participation_cap() -> None:
    adv = {"A": 1000.0, "B": 2000.0}
    tradable = {"A": True, "B": False}

    report = run_capacity(adv, tradable, model())

    assert report.per_name[0].instrument_id == "A"
    assert report.per_name[0].capacity == pytest.approx(10.0)  # 1000 * 0.01
    assert report.per_name[1].instrument_id == "B"
    assert report.per_name[1].capacity == 0.0  # not tradable


def test_total_capacity_sums_tradable_names() -> None:
    adv = {"A": 1000.0, "B": 2000.0, "C": 3000.0}
    tradable = {"A": True, "B": True, "C": False}

    report = run_capacity(adv, tradable, model())

    assert report.total_capacity == pytest.approx(30.0)  # (1000 + 2000) * 0.01
    assert report.tradable_count == 2


def test_aum_curve_is_monotonic() -> None:
    adv = {"A": 1000.0, "B": 2000.0}
    tradable = {"A": True, "B": True}

    report = run_capacity(adv, tradable, model())

    aums = [point.aum for point in report.aum_curve]
    assert all(first < second for first, second in zip(aums, aums[1:], strict=False))


def test_rejects_invalid_participation_steps() -> None:
    adv = {"A": 1000.0}

    with pytest.raises(ValueError):
        run_capacity(adv, {"A": True}, model(), participation_steps=(0.02, 0.01))


def test_rejects_invalid_market() -> None:
    with pytest.raises(ValueError):
        CapacityModel(
            market="NYSE",
            max_adv_participation=0.01,
            impact_coefficient=0.1,
            margin_rate=1.0,
            exclude_limit_up_down=True,
            exclude_suspended=True,
        )


def test_rejects_non_positive_adv() -> None:
    adv = {"A": 0.0}

    with pytest.raises(ValueError):
        run_capacity(adv, {"A": True}, model())
