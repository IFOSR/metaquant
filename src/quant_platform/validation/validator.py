"""Deterministic single-factor validator (G4-003).

Computes data-quality (Gate 1) and predictive-power (Gate 2) statistics from a
sealed factor computation artifact and a sealed forward-return label series.
All statistics use stable ordering and fixed floating-point reductions so the
report hash is reproducible.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from itertools import pairwise

from quant_platform.experiments import (
    FactorComputationArtifact,
    canonical_hash,
)
from quant_platform.validation import (
    LabelSeries,
    ValidationPolicy,
)


@dataclass(frozen=True, slots=True)
class CrossSection:
    """One time slice of aligned (factor, label) pairs."""

    event_time: datetime
    pairs: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    observation_count: int
    finite_count: int
    coverage_ratio: float
    constant_ratio: float


@dataclass(frozen=True, slots=True)
class QuantileReturn:
    quantile: int
    mean_return: float | None


@dataclass(frozen=True, slots=True)
class PredictivePowerReport:
    mean_pearson_ic: float | None
    mean_rank_ic: float | None
    icir: float | None
    nw_t: float | None
    ic_decay: tuple[tuple[int, float | None], ...]
    quantile_returns: tuple[QuantileReturn, ...]
    top_bottom_spread: float | None
    monotonic: bool | None


@dataclass(frozen=True, slots=True)
class FactorValidationReport:
    policy_id: str
    policy_hash: str
    label_id: str
    label_hash: str
    factor_artifact_hash: str
    data_quality: DataQualityReport
    predictive_power: PredictivePowerReport
    output_hash: str

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "factor-validation/v1",
            "policy_id": self.policy_id,
            "policy_hash": self.policy_hash,
            "label_id": self.label_id,
            "label_hash": self.label_hash,
            "factor_artifact_hash": self.factor_artifact_hash,
            "data_quality": {
                "observation_count": self.data_quality.observation_count,
                "finite_count": self.data_quality.finite_count,
                "coverage_ratio": self.data_quality.coverage_ratio,
                "constant_ratio": self.data_quality.constant_ratio,
            },
            "predictive_power": {
                "mean_pearson_ic": self.predictive_power.mean_pearson_ic,
                "mean_rank_ic": self.predictive_power.mean_rank_ic,
                "icir": self.predictive_power.icir,
                "nw_t": self.predictive_power.nw_t,
                "ic_decay": [
                    {"horizon": horizon, "mean_ic": value}
                    for horizon, value in self.predictive_power.ic_decay
                ],
                "quantile_returns": [
                    {"quantile": item.quantile, "mean_return": item.mean_return}
                    for item in self.predictive_power.quantile_returns
                ],
                "top_bottom_spread": self.predictive_power.top_bottom_spread,
                "monotonic": self.predictive_power.monotonic,
            },
        }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _pearson(xs: list[float], ys: list[float]) -> float:
    mx = _mean(xs)
    my = _mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0.0 or vy == 0.0:
        return 0.0
    return cov / math.sqrt(vx * vy)


def _average_ranks(values: list[float]) -> list[float]:
    """1-based average ranks with stable tie handling."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        average = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[order[k]] = average
        i = j
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float:
    return _pearson(_average_ranks(xs), _average_ranks(ys))


def _nw_t(series: list[float], lag: int = 1) -> float:
    n = len(series)
    if n < 2:
        return 0.0
    mean = _mean(series)
    residuals = [value - mean for value in series]
    variance = sum(r * r for r in residuals) / n
    covariance = 0.0
    for step in range(1, min(lag, n - 1) + 1):
        weight = 1.0 - step / (lag + 1)
        covariance += (
            weight
            * 2.0
            * sum(residuals[i] * residuals[i + step] for i in range(n - step))
            / n
        )
    long_run_variance = variance + covariance
    if long_run_variance <= 0.0:
        return 0.0
    return mean / math.sqrt(long_run_variance / n)


def align_cross_sections(
    factor: FactorComputationArtifact,
    label: LabelSeries,
) -> tuple[CrossSection, ...]:
    """Align factor and label observations by instrument and event time."""
    factor_by_key = {
        (item.instrument_id, item.event_time): item.value
        for item in factor.observations
        if item.value is not None
    }
    label_by_time: dict[datetime, list[tuple[str, float]]] = {}
    for item in label.observations:
        if item.value is None:
            continue
        label_by_time.setdefault(item.event_time, []).append(
            (item.instrument_id, item.value)
        )

    sections: list[CrossSection] = []
    for event_time in sorted(label_by_time):
        pairs: list[tuple[float, float]] = []
        for instrument_id, label_value in label_by_time[event_time]:
            factor_value = factor_by_key.get((instrument_id, event_time))
            if factor_value is not None:
                pairs.append((factor_value, label_value))
        if len(pairs) >= 2:
            sections.append(CrossSection(event_time, tuple(sorted(pairs))))
    return tuple(sections)


def _quantile_returns(
    sections: tuple[CrossSection, ...], quantile_count: int
) -> tuple[QuantileReturn, ...]:
    buckets: list[list[float]] = [[] for _ in range(quantile_count)]
    for section in sections:
        pairs = sorted(section.pairs, key=lambda pair: pair[0])
        n = len(pairs)
        for q in range(quantile_count):
            lo = q * n // quantile_count
            hi = (q + 1) * n // quantile_count
            bucket = [label for _, label in pairs[lo:hi]]
            if bucket:
                buckets[q].append(_mean(bucket))
    return tuple(
        QuantileReturn(q + 1, _mean(bucket) if bucket else None)
        for q, bucket in enumerate(buckets)
    )


def validate_factor(
    factor: FactorComputationArtifact,
    label: LabelSeries,
    policy: ValidationPolicy,
) -> FactorValidationReport:
    sections = align_cross_sections(factor, label)

    factor_values = [
        item.value for item in factor.observations if item.value is not None
    ]
    coverage = (
        len(factor_values) / len(factor.observations) if factor.observations else 0.0
    )
    constant_ratio = (
        Counter(factor_values).most_common(1)[0][1] / len(factor_values)
        if factor_values
        else 0.0
    )
    data_quality = DataQualityReport(
        observation_count=len(factor.observations),
        finite_count=len(factor_values),
        coverage_ratio=coverage,
        constant_ratio=constant_ratio,
    )

    pearson_ics: list[float] = []
    rank_ics: list[float] = []
    for section in sections:
        xs = [pair[0] for pair in section.pairs]
        ys = [pair[1] for pair in section.pairs]
        pearson_ics.append(_pearson(xs, ys))
        rank_ics.append(_spearman(xs, ys))

    mean_pearson_ic = _mean(pearson_ics) if pearson_ics else None
    mean_rank_ic = _mean(rank_ics) if rank_ics else None
    icir = (
        _mean(pearson_ics) / _stddev(pearson_ics)
        if pearson_ics and _stddev(pearson_ics) > 0.0
        else None
    )
    nw_t = _nw_t(pearson_ics) if pearson_ics else None

    quantile_returns = _quantile_returns(sections, policy.quantile_count)
    non_null = [
        item.mean_return for item in quantile_returns if item.mean_return is not None
    ]
    top_bottom_spread = non_null[-1] - non_null[0] if len(non_null) >= 2 else None
    monotonic = _monotonic(non_null) if len(non_null) >= 2 else None

    predictive_power = PredictivePowerReport(
        mean_pearson_ic=mean_pearson_ic,
        mean_rank_ic=mean_rank_ic,
        icir=icir,
        nw_t=nw_t,
        ic_decay=((label.label.horizon, mean_pearson_ic),),
        quantile_returns=quantile_returns,
        top_bottom_spread=top_bottom_spread,
        monotonic=monotonic,
    )

    report = FactorValidationReport(
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash(),
        label_id=label.label.label_id,
        label_hash=label.content_hash(),
        factor_artifact_hash=factor.manifest.content_hash,
        data_quality=data_quality,
        predictive_power=predictive_power,
        output_hash="",
    )
    return replace(report, output_hash=canonical_hash(report.payload()))


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _monotonic(values: list[float]) -> bool:
    increasing = all(a <= b for a, b in pairwise(values))
    decreasing = all(a >= b for a, b in pairwise(values))
    return increasing or decreasing
