"""Walk-forward out-of-sample validation (G16-001, FR-403).

Splits a time-ordered series into rolling train / embargo / test windows and
computes out-of-sample IC aggregates per split. The output is content-addressed
so downstream gates (promotion) can reference it as an artifact instead of
trusting caller-supplied numbers.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date

from quant_platform.experiments import canonical_hash


@dataclass(frozen=True, slots=True)
class OOSSplit:
    split_id: str
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    def payload(self) -> dict[str, object]:
        return {
            "split_id": self.split_id,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class OOSReport:
    splits: tuple[OOSSplit, ...]
    train_ics: tuple[float, ...]
    test_ics: tuple[float, ...]
    embargo_days: int

    def __post_init__(self) -> None:
        if len(self.train_ics) != len(self.splits) or len(self.test_ics) != len(
            self.splits
        ):
            raise ValueError("ic tuples must match the number of splits")
        if not self.splits:
            raise ValueError("splits must not be empty")
        for value in (*self.train_ics, *self.test_ics):
            if not math.isfinite(value):
                raise ValueError("ic values must be finite")

    @property
    def oos_ic_mean(self) -> float:
        return statistics.fmean(self.test_ics)

    @property
    def oos_ic_std(self) -> float:
        if len(self.test_ics) < 2:
            return 0.0
        return statistics.stdev(self.test_ics)

    @property
    def oos_ic_ir(self) -> float:
        if self.oos_ic_std <= 0.0:
            return 0.0
        return self.oos_ic_mean / self.oos_ic_std

    @property
    def oos_hit_rate(self) -> float:
        return sum(1 for value in self.test_ics if value > 0.0) / len(self.test_ics)

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "oos-report/v1",
            "embargo_days": self.embargo_days,
            "splits": [item.payload() for item in self.splits],
            "train_ics": list(self.train_ics),
            "test_ics": list(self.test_ics),
            "oos_ic_mean": self.oos_ic_mean,
            "oos_ic_std": self.oos_ic_std,
            "oos_ic_ir": self.oos_ic_ir,
            "oos_hit_rate": self.oos_hit_rate,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def split_walk_forward(
    dates: tuple[date, ...],
    *,
    n_splits: int,
    train_ratio: float,
    test_ratio: float,
    embargo_days: int,
) -> tuple[OOSSplit, ...]:
    """Roll the train/embargo/test windows forward over ``dates``.

    Windows are indexed by trading-day position, so ``embargo_days`` is the
    number of trading days between the last train day and the first test day.
    If the requested geometry does not fit the date range, the split sequence
    is truncated; if no split fits, ``ValueError`` is raised.
    """
    if not dates or len(set(dates)) != len(dates):
        raise ValueError("dates must be a non-empty unique sequence")
    if any(second <= first for first, second in zip(dates, dates[1:], strict=False)):
        raise ValueError("dates must be strictly increasing")
    if n_splits < 1:
        raise ValueError("n_splits must be positive")
    if not (0.0 < train_ratio < 1.0 and 0.0 < test_ratio < 1.0):
        raise ValueError("train_ratio and test_ratio must be within (0, 1)")
    if train_ratio + test_ratio >= 1.0:
        raise ValueError("train + test ratios must leave room for embargo")
    if embargo_days < 0:
        raise ValueError("embargo_days must be non-negative")

    total = len(dates)
    train_len = int(total * train_ratio)
    test_len = int(total * test_ratio)
    if train_len < 2 or test_len < 2:
        raise ValueError("window sizes too small for the given ratios")

    if n_splits == 1:
        stride = 0
    else:
        usable = total - train_len - test_len - embargo_days
        stride = max(1, usable // (n_splits - 1))

    splits: list[OOSSplit] = []
    for index in range(n_splits):
        train_start = index * stride
        train_end = train_start + train_len - 1
        test_start = train_end + embargo_days + 1
        test_end = test_start + test_len - 1
        if test_end >= total:
            break
        splits.append(
            OOSSplit(
                split_id=f"split_{index + 1}",
                train_start=dates[train_start],
                train_end=dates[train_end],
                test_start=dates[test_start],
                test_end=dates[test_end],
            )
        )
    if not splits:
        raise ValueError("not enough dates for the requested split geometry")
    return tuple(splits)


def run_oos_validation(
    dates: tuple[date, ...],
    ic_series: tuple[float, ...],
    *,
    n_splits: int = 4,
    train_ratio: float = 0.6,
    test_ratio: float = 0.2,
    embargo_days: int = 5,
) -> OOSReport:
    """Compute per-split train and out-of-sample IC from a daily IC series.

    ``ic_series`` must align with ``dates`` (one IC per day). Each split
    averages the IC over its train window and over its disjoint test window.
    """
    if len(ic_series) != len(dates):
        raise ValueError("ic_series must align with dates")
    for value in ic_series:
        if not math.isfinite(value):
            raise ValueError("ic values must be finite")

    splits = split_walk_forward(
        dates,
        n_splits=n_splits,
        train_ratio=train_ratio,
        test_ratio=test_ratio,
        embargo_days=embargo_days,
    )
    date_index = {day: position for position, day in enumerate(dates)}
    train_ics: list[float] = []
    test_ics: list[float] = []
    for split in splits:
        train_start = date_index[split.train_start]
        train_end = date_index[split.train_end]
        test_start = date_index[split.test_start]
        test_end = date_index[split.test_end]
        train_ics.append(statistics.fmean(ic_series[train_start : train_end + 1]))
        test_ics.append(statistics.fmean(ic_series[test_start : test_end + 1]))
    return OOSReport(
        splits=splits,
        train_ics=tuple(train_ics),
        test_ics=tuple(test_ics),
        embargo_days=embargo_days,
    )
