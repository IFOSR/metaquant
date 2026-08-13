"""Robustness and false-discovery contracts (G5).

G5-002 delivers negative controls: a factor's observed IC is compared against
deterministically shuffled and time-shifted labels run through the same
validator, so the comparison is apples-to-apples and reproducible.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from quant_platform.experiments import FactorComputationArtifact, canonical_hash
from quant_platform.validation.contracts import LabelObservation, LabelSeries
from quant_platform.validation.policy import ValidationPolicy
from quant_platform.validation.validator import FactorValidationReport, validate_factor


def _primary_ic(report: FactorValidationReport) -> float | None:
    predictive = report.predictive_power
    if predictive.mean_pearson_ic is not None:
        return predictive.mean_pearson_ic
    return predictive.mean_rank_ic


def _shuffled_label(label: LabelSeries, seed: int) -> LabelSeries:
    values = [obs.value for obs in label.observations]
    rng = random.Random(seed)
    rng.shuffle(values)
    return LabelSeries(
        label=label.label,
        observations=tuple(
            LabelObservation(obs.instrument_id, obs.event_time, values[i])
            for i, obs in enumerate(label.observations)
        ),
    )


def _time_shifted_label(label: LabelSeries) -> LabelSeries:
    values = [obs.value for obs in label.observations]
    if len(values) > 1:
        values = values[1:] + values[:1]
    return LabelSeries(
        label=label.label,
        observations=tuple(
            LabelObservation(obs.instrument_id, obs.event_time, values[i])
            for i, obs in enumerate(label.observations)
        ),
    )


def _percentile(values: tuple[float, ...], target: float) -> float:
    if not values:
        return 0.0
    below = sum(1 for value in values if value <= target)
    return below / len(values)


@dataclass(frozen=True, slots=True)
class NegativeControlReport:
    observed_ic: float | None
    shuffled_ics: tuple[float, ...]
    time_shifted_ic: float | None
    percentile: float

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "negative-control/v1",
            "observed_ic": self.observed_ic,
            "shuffled_ics": list(self.shuffled_ics),
            "time_shifted_ic": self.time_shifted_ic,
            "percentile": self.percentile,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def run_negative_controls(
    factor: FactorComputationArtifact,
    label: LabelSeries,
    policy: ValidationPolicy,
    *,
    n_shuffles: int = 100,
    seed: int = 0,
) -> NegativeControlReport:
    observed = _primary_ic(validate_factor(factor, label, policy))
    shuffled: list[float] = []
    for index in range(n_shuffles):
        ic = _primary_ic(
            validate_factor(factor, _shuffled_label(label, seed + index), policy)
        )
        if ic is not None:
            shuffled.append(ic)
    time_shifted = _primary_ic(
        validate_factor(factor, _time_shifted_label(label), policy)
    )
    percentile = _percentile(tuple(shuffled), observed) if observed is not None else 0.0
    return NegativeControlReport(
        observed_ic=observed,
        shuffled_ics=tuple(shuffled),
        time_shifted_ic=time_shifted,
        percentile=percentile,
    )
