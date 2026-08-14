"""Turnover analysis contracts (G6-003).

A ``FactorSeries`` is a strictly time-ordered sequence of cross-sections.
``run_turnover`` computes raw one-period weight turnover, buffered turnover
(the fraction of names whose rank change exceeds a buffer), and signal
half-life from the lag-1 autocorrelation of cross-sectional means.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from quant_platform.experiments import (
    FactorComputationArtifact,
    FactorObservation,
    canonical_hash,
)


def _section_time(cross_section: FactorComputationArtifact) -> datetime:
    return cross_section.observations[0].event_time


@dataclass(frozen=True, slots=True)
class FactorSeries:
    cross_sections: tuple[FactorComputationArtifact, ...]

    def __post_init__(self) -> None:
        if len(self.cross_sections) < 2:
            raise ValueError("factor series requires at least two cross-sections")
        if any(len(cs.observations) == 0 for cs in self.cross_sections):
            raise ValueError("factor series cross-sections must not be empty")
        for cs in self.cross_sections:
            ids = [obs.instrument_id for obs in cs.observations]
            if len(set(ids)) != len(ids):
                raise ValueError(
                    "factor series cross-sections must have unique instruments"
                )
        times = [_section_time(cs) for cs in self.cross_sections]
        if any(
            second <= first for first, second in zip(times, times[1:], strict=False)
        ):
            raise ValueError(
                "factor series cross-sections must be strictly time-ordered"
            )


def _aligned_pair(
    first: FactorComputationArtifact, second: FactorComputationArtifact
) -> tuple[list[float], list[float]]:
    second_map = {
        obs.instrument_id: obs.value
        for obs in second.observations
        if obs.value is not None
    }
    first_values: list[float] = []
    second_values: list[float] = []
    for obs in first.observations:
        if obs.value is None:
            continue
        matched = second_map.get(obs.instrument_id)
        if matched is not None:
            first_values.append(obs.value)
            second_values.append(matched)
    return first_values, second_values


def _normalize(values: list[float]) -> list[float]:
    total = sum(abs(value) for value in values)
    if total == 0.0:
        return [1.0 / len(values) for _ in values]
    return [value / total for value in values]


def _weight_turnover(
    first: FactorComputationArtifact, second: FactorComputationArtifact
) -> float:
    first_values, second_values = _aligned_pair(first, second)
    if not first_values:
        return 0.0
    first_weights = _normalize(first_values)
    second_weights = _normalize(second_values)
    return 0.5 * sum(
        abs(a - b) for a, b in zip(first_weights, second_weights, strict=True)
    )


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for position, index in enumerate(order):
        ranks[index] = float(position)
    return ranks


def _buffered_turnover(
    first: FactorComputationArtifact,
    second: FactorComputationArtifact,
    buffer: float,
) -> float:
    first_values, second_values = _aligned_pair(first, second)
    count = len(first_values)
    if count == 0:
        return 0.0
    first_ranks = _rank(first_values)
    second_ranks = _rank(second_values)
    changed = sum(
        1
        for index in range(count)
        if abs(first_ranks[index] - second_ranks[index]) / count > buffer
    )
    return changed / count


def _autocorrelation(values: list[float]) -> float:
    count = len(values)
    if count < 2:
        return 0.0
    mean = sum(values) / count
    numerator = sum(
        (values[index] - mean) * (values[index + 1] - mean)
        for index in range(count - 1)
    )
    denominator = sum((value - mean) ** 2 for value in values)
    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def _half_life(autocorrelation: float) -> float | None:
    if autocorrelation <= 0.0 or autocorrelation >= 1.0:
        return None
    return math.log(0.5) / math.log(autocorrelation)


@dataclass(frozen=True, slots=True)
class TurnoverReport:
    raw_turnover: float
    buffered_turnover: float
    signal_half_life: float | None
    period_count: int

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "turnover/v1",
            "raw_turnover": self.raw_turnover,
            "buffered_turnover": self.buffered_turnover,
            "signal_half_life": self.signal_half_life,
            "period_count": self.period_count,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def run_turnover(series: FactorSeries, *, buffer: float = 0.1) -> TurnoverReport:
    cross_sections = series.cross_sections
    raw = [
        _weight_turnover(first, second)
        for first, second in zip(cross_sections, cross_sections[1:], strict=False)
    ]
    buffered = [
        _buffered_turnover(first, second, buffer)
        for first, second in zip(cross_sections, cross_sections[1:], strict=False)
    ]
    means = [
        sum(obs.value for obs in cs.observations if obs.value is not None)
        / max(
            1,
            sum(1 for obs in cs.observations if obs.value is not None),
        )
        for cs in cross_sections
    ]
    half_life = _half_life(_autocorrelation(means))
    return TurnoverReport(
        raw_turnover=sum(raw) / len(raw),
        buffered_turnover=sum(buffered) / len(buffered),
        signal_half_life=half_life,
        period_count=len(cross_sections),
    )


def build_factor_series(factor: FactorComputationArtifact) -> FactorSeries:
    """Split a multi-period factor artifact into time-ordered cross-sections.

    This is the historical ``FactorSeries`` execution path: a single sealed
    computation artifact whose observations span multiple event times is split
    into one single-period artifact per event time, then wrapped as a strictly
    time-ordered ``FactorSeries`` ready for ``run_turnover``.
    """
    by_time: dict[datetime, list[FactorObservation]] = {}
    for observation in factor.observations:
        by_time.setdefault(observation.event_time, []).append(observation)

    sections: list[FactorComputationArtifact] = []
    for index, (_, observations) in enumerate(sorted(by_time.items())):
        sections.append(
            FactorComputationArtifact.create(
                artifact_id=f"{factor.artifact_id}-t{index}",
                run_id=factor.run_id,
                attempt_id=factor.attempt_id,
                experiment_spec_hash=factor.experiment_spec_hash,
                factor_ir_hash=factor.factor_ir_hash,
                snapshot_id=factor.snapshot_id,
                snapshot_manifest_hash=factor.snapshot_manifest_hash,
                input_hash=factor.input_hash,
                observations=tuple(observations),
            )
        )
    return FactorSeries(cross_sections=tuple(sections))
