from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.experiments import FactorComputationArtifact, FactorObservation
from quant_platform.validation import (
    ForwardReturnLabel,
    ICSign,
    LabelObservation,
    LabelSeries,
    ValidationPolicy,
    run_negative_controls,
)


def at(day: int) -> datetime:
    return datetime(2026, 8, day, 15, tzinfo=UTC)


def factor(*observations: FactorObservation) -> FactorComputationArtifact:
    return FactorComputationArtifact.create(
        artifact_id="artifact-001",
        run_id="run-001",
        attempt_id="attempt-001",
        experiment_spec_hash="1" * 64,
        factor_ir_hash="2" * 64,
        snapshot_id="snapshot-001",
        snapshot_manifest_hash="3" * 64,
        input_hash="4" * 64,
        observations=observations,
    )


def label(*observations: LabelObservation) -> LabelSeries:
    return LabelSeries(
        label=ForwardReturnLabel(
            label_id="label-001",
            market="CN_A",
            horizon=5,
            field_ref="market.eod.forward_return_5d",
        ),
        observations=observations,
    )


def policy() -> ValidationPolicy:
    return ValidationPolicy(
        policy_id="policy://cn-a-daily-factor/v1",
        market="CN_A",
        min_coverage=0.0,
        min_observations=1,
        max_constant_ratio=1.0,
        ic_sign=ICSign.ANY,
        min_icir=0.0,
        min_nw_t=0.0,
        quantile_count=2,
        decay_horizons=(5,),
    )


def perfect_factor_and_label() -> tuple[FactorComputationArtifact, LabelSeries]:
    artifact = factor(
        FactorObservation("A", at(1), 1.0),
        FactorObservation("B", at(1), 2.0),
        FactorObservation("C", at(1), 3.0),
        FactorObservation("D", at(1), 4.0),
    )
    series = label(
        LabelObservation("A", at(1), 0.1),
        LabelObservation("B", at(1), 0.2),
        LabelObservation("C", at(1), 0.3),
        LabelObservation("D", at(1), 0.4),
    )
    return artifact, series


def test_run_negative_controls_is_deterministic() -> None:
    artifact, series = perfect_factor_and_label()

    first = run_negative_controls(artifact, series, policy(), n_shuffles=20, seed=7)
    second = run_negative_controls(artifact, series, policy(), n_shuffles=20, seed=7)

    assert first == second
    assert first.content_hash() == second.content_hash()


def test_perfect_factor_beats_shuffled_controls() -> None:
    artifact, series = perfect_factor_and_label()

    report = run_negative_controls(artifact, series, policy(), n_shuffles=100, seed=0)

    assert report.observed_ic == pytest.approx(1.0)
    assert report.percentile == 1.0
    assert len(report.shuffled_ics) == 100


def test_shuffled_ics_are_weaker_on_average() -> None:
    artifact, series = perfect_factor_and_label()

    report = run_negative_controls(artifact, series, policy(), n_shuffles=100, seed=1)

    assert report.observed_ic is not None
    shuffled_mean = sum(report.shuffled_ics) / len(report.shuffled_ics)
    assert shuffled_mean < report.observed_ic


def test_time_shifted_ic_breaks_perfect_correlation() -> None:
    artifact, series = perfect_factor_and_label()

    report = run_negative_controls(artifact, series, policy(), n_shuffles=5, seed=2)

    assert report.time_shifted_ic is not None
    assert report.time_shifted_ic < 1.0


def test_percentile_is_zero_for_empty_controls() -> None:
    # a single observation produces no Pearson IC, so percentile is zero.
    artifact = factor(FactorObservation("A", at(1), 1.0))
    series = label(LabelObservation("A", at(1), 0.1))

    report = run_negative_controls(artifact, series, policy(), n_shuffles=3, seed=0)

    assert report.observed_ic is None
    assert report.percentile == 0.0
