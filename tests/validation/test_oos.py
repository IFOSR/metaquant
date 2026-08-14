from __future__ import annotations

from datetime import date, timedelta

import pytest

from quant_platform.validation.oos import (
    run_oos_validation,
    split_walk_forward,
)


def trading_days(count: int) -> tuple[date, ...]:
    start = date(2024, 1, 1)
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def test_split_walk_forward_geometry() -> None:
    days = trading_days(100)
    splits = split_walk_forward(
        days, n_splits=4, train_ratio=0.6, test_ratio=0.2, embargo_days=5
    )

    assert len(splits) >= 2
    for split in splits:
        # train and test never overlap
        assert split.train_end < split.test_start
        # windows are strictly ordered
        assert split.train_start <= split.train_end
        assert split.test_start <= split.test_end


def test_embargo_separates_train_and_test() -> None:
    days = trading_days(100)
    embargo = 5
    splits = split_walk_forward(
        days, n_splits=4, train_ratio=0.6, test_ratio=0.2, embargo_days=embargo
    )

    positions = {day: index for index, day in enumerate(days)}
    for split in splits:
        gap = positions[split.test_start] - positions[split.train_end] - 1
        assert gap >= embargo


def test_oos_report_aggregates() -> None:
    days = trading_days(60)
    # train ICs positive, OOS ICs negative -> mean sign flips
    ic = [0.05 if index < 30 else -0.02 for index in range(len(days))]
    report = run_oos_validation(days, tuple(ic), n_splits=2)

    assert report.oos_ic_mean == pytest.approx(-0.02)
    assert report.oos_hit_rate == pytest.approx(0.0)
    assert report.content_hash() == report.content_hash()


def test_oos_report_rejects_mismatched_series() -> None:
    days = trading_days(60)
    with pytest.raises(ValueError):
        run_oos_validation(days, (0.1,) * 10)


def test_split_rejects_invalid_ratios() -> None:
    days = trading_days(60)
    with pytest.raises(ValueError):
        split_walk_forward(
            days, n_splits=4, train_ratio=0.7, test_ratio=0.5, embargo_days=5
        )
    with pytest.raises(ValueError):
        split_walk_forward(
            days, n_splits=4, train_ratio=0.0, test_ratio=0.2, embargo_days=5
        )


def test_split_rejects_unordered_dates() -> None:
    days = trading_days(60)
    reversed_days = tuple(reversed(days))
    with pytest.raises(ValueError):
        split_walk_forward(
            reversed_days, n_splits=4, train_ratio=0.6, test_ratio=0.2, embargo_days=5
        )


def test_oos_report_rejects_non_finite_ic() -> None:
    days = trading_days(60)
    with pytest.raises(ValueError):
        run_oos_validation(days, (float("nan"),) * len(days))
