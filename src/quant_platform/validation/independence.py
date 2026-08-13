"""Independence analysis contracts (G6-002).

Given a candidate factor, the factors already in the Alpha Pool (aligned on the
same cross-section), and the label, this module reports cross-sectional
correlation with each pool factor, the candidate's incremental IC after
orthogonalization, and whether the candidate unintentionally replicates a known
factor.
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
from quant_platform.validation.contracts import LabelSeries
from quant_platform.validation.policy import ValidationPolicy
from quant_platform.validation.validator import FactorValidationReport, validate_factor


def _primary_ic(report: FactorValidationReport) -> float | None:
    predictive = report.predictive_power
    if predictive.mean_pearson_ic is not None:
        return predictive.mean_pearson_ic
    return predictive.mean_rank_ic


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    if variance_x == 0.0 or variance_y == 0.0:
        return None
    return covariance / math.sqrt(variance_x * variance_y)


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        average = (index + end) / 2 + 1  # 1-based average rank for ties
        for position in range(index, end + 1):
            ranks[order[position]] = float(average)
        index = end + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    return _pearson(_rank(xs), _rank(ys))


def _aligned_pair(
    first: FactorComputationArtifact, second: FactorComputationArtifact
) -> tuple[list[float], list[float]]:
    second_map = {
        (obs.instrument_id, obs.event_time): obs.value
        for obs in second.observations
        if obs.value is not None
    }
    first_values: list[float] = []
    second_values: list[float] = []
    for obs in first.observations:
        if obs.value is None:
            continue
        matched = second_map.get((obs.instrument_id, obs.event_time))
        if matched is not None:
            first_values.append(obs.value)
            second_values.append(matched)
    return first_values, second_values


def _common_keys(
    factors: list[FactorComputationArtifact],
) -> list[tuple[str, datetime]]:
    keys = {
        (obs.instrument_id, obs.event_time)
        for obs in factors[0].observations
        if obs.value is not None
    }
    for factor in factors[1:]:
        keys &= {
            (obs.instrument_id, obs.event_time)
            for obs in factor.observations
            if obs.value is not None
        }
    return sorted(keys)


def _aligned_values(
    factor: FactorComputationArtifact, keys: list[tuple[str, datetime]]
) -> list[float]:
    mapping = {
        (obs.instrument_id, obs.event_time): obs.value
        for obs in factor.observations
        if obs.value is not None
    }
    return [mapping[key] for key in keys]


def _orthogonalized_candidate(
    candidate: FactorComputationArtifact,
    pool_factors: tuple[FactorComputationArtifact, ...],
) -> FactorComputationArtifact:
    if not pool_factors:
        return candidate
    factors = [candidate, *pool_factors]
    keys = _common_keys(factors)
    if len(keys) < 2:
        return candidate
    residual = _aligned_values(candidate, keys)
    residual_mean = sum(residual) / len(residual)
    residual = [value - residual_mean for value in residual]
    for pool in pool_factors:
        pool_values = _aligned_values(pool, keys)
        pool_mean = sum(pool_values) / len(pool_values)
        centered = [value - pool_mean for value in pool_values]
        denominator = sum(value * value for value in centered)
        if denominator == 0.0:
            continue
        beta = sum(r * p for r, p in zip(residual, centered, strict=True)) / denominator
        residual = [r - beta * p for r, p in zip(residual, centered, strict=True)]
    observations = tuple(
        FactorObservation(instrument_id, event_time, value)
        for (instrument_id, event_time), value in zip(keys, residual, strict=True)
    )
    return FactorComputationArtifact.create(
        artifact_id=f"{candidate.artifact_id}-orth",
        run_id=candidate.run_id,
        attempt_id=candidate.attempt_id,
        experiment_spec_hash=candidate.experiment_spec_hash,
        factor_ir_hash=candidate.factor_ir_hash,
        snapshot_id=candidate.snapshot_id,
        snapshot_manifest_hash=candidate.snapshot_manifest_hash,
        input_hash=candidate.input_hash,
        observations=observations,
    )


@dataclass(frozen=True, slots=True)
class PairwiseCorrelation:
    factor_ir_hash: str
    pearson: float | None
    spearman: float | None

    def payload(self) -> dict[str, object]:
        return {
            "factor_ir_hash": self.factor_ir_hash,
            "pearson": self.pearson,
            "spearman": self.spearman,
        }


@dataclass(frozen=True, slots=True)
class IndependenceReport:
    baseline_ic: float | None
    orthogonalized_ic: float | None
    pairwise: tuple[PairwiseCorrelation, ...]
    max_abs_correlation: float | None
    replicated_risk_factor: bool

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "independence/v1",
            "baseline_ic": self.baseline_ic,
            "orthogonalized_ic": self.orthogonalized_ic,
            "pairwise": [item.payload() for item in self.pairwise],
            "max_abs_correlation": self.max_abs_correlation,
            "replicated_risk_factor": self.replicated_risk_factor,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def run_independence_analysis(
    candidate: FactorComputationArtifact,
    pool_factors: tuple[FactorComputationArtifact, ...],
    label: LabelSeries,
    policy: ValidationPolicy,
    *,
    correlation_threshold: float = 0.8,
) -> IndependenceReport:
    baseline = _primary_ic(validate_factor(candidate, label, policy))
    pairwise = tuple(
        PairwiseCorrelation(
            factor_ir_hash=pool.factor_ir_hash,
            pearson=_pearson(*_aligned_pair(candidate, pool)),
            spearman=_spearman(*_aligned_pair(candidate, pool)),
        )
        for pool in pool_factors
    )
    correlations = [
        value
        for item in pairwise
        for value in (item.pearson, item.spearman)
        if value is not None
    ]
    max_abs = max((abs(value) for value in correlations), default=None)
    orthogonalized = _orthogonalized_candidate(candidate, pool_factors)
    orthogonalized_ic = _primary_ic(validate_factor(orthogonalized, label, policy))
    replicated = max_abs is not None and max_abs > correlation_threshold
    return IndependenceReport(
        baseline_ic=baseline,
        orthogonalized_ic=orthogonalized_ic,
        pairwise=pairwise,
        max_abs_correlation=max_abs,
        replicated_risk_factor=replicated,
    )
