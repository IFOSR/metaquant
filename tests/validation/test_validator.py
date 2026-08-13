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
    align_cross_sections,
    validate_factor,
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
        min_coverage=0.8,
        min_observations=120,
        max_constant_ratio=0.9,
        ic_sign=ICSign.ANY,
        min_icir=0.3,
        min_nw_t=2.0,
        quantile_count=3,
        decay_horizons=(5,),
    )


def test_align_cross_sections_matches_instrument_and_time() -> None:
    artifact = factor(
        FactorObservation("A", at(1), 1.0),
        FactorObservation("B", at(1), 2.0),
        FactorObservation("A", at(2), 3.0),
    )
    series = label(
        LabelObservation("A", at(1), 10.0),
        LabelObservation("B", at(1), 20.0),
        LabelObservation("A", at(2), 30.0),
        LabelObservation("C", at(1), 99.0),  # no factor value -> excluded
    )

    sections = align_cross_sections(artifact, series)

    assert len(sections) == 1
    assert sections[0].pairs == ((1.0, 10.0), (2.0, 20.0))


def test_validate_factor_perfect_positive_ic() -> None:
    artifact = factor(
        FactorObservation("A", at(1), 1.0),
        FactorObservation("B", at(1), 2.0),
        FactorObservation("C", at(1), 3.0),
    )
    series = label(
        LabelObservation("A", at(1), 1.0),
        LabelObservation("B", at(1), 2.0),
        LabelObservation("C", at(1), 3.0),
    )

    report = validate_factor(artifact, series, policy())

    assert report.predictive_power.mean_pearson_ic == pytest.approx(1.0)
    assert report.predictive_power.mean_rank_ic == pytest.approx(1.0)
    assert report.data_quality.constant_ratio == pytest.approx(1.0 / 3.0)


def test_rank_ic_invariant_to_monotone_transform() -> None:
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

    report = validate_factor(artifact, series, policy())

    assert report.predictive_power.mean_rank_ic == pytest.approx(1.0)


def test_validate_factor_is_deterministic() -> None:
    artifact = factor(
        FactorObservation("A", at(1), 1.0),
        FactorObservation("B", at(1), 2.0),
    )
    series = label(
        LabelObservation("A", at(1), 0.1),
        LabelObservation("B", at(1), 0.2),
    )

    first = validate_factor(artifact, series, policy())
    second = validate_factor(artifact, series, policy())

    assert first.output_hash == second.output_hash
    assert len(first.output_hash) == 64
