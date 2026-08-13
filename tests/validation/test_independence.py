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
    run_independence_analysis,
)


def at(day: int) -> datetime:
    return datetime(2026, 8, day, 15, tzinfo=UTC)


def factor(*observations: FactorObservation) -> FactorComputationArtifact:
    return FactorComputationArtifact.create(
        artifact_id="artifact-001",
        run_id="run-001",
        attempt_id="attempt-001",
        experiment_spec_hash="1" * 64,
        factor_ir_hash="a" * 64,
        snapshot_id="snapshot-001",
        snapshot_manifest_hash="3" * 64,
        input_hash="4" * 64,
        observations=observations,
    )


def pool_factor(*observations: FactorObservation) -> FactorComputationArtifact:
    return FactorComputationArtifact.create(
        artifact_id="artifact-pool",
        run_id="run-001",
        attempt_id="attempt-001",
        experiment_spec_hash="1" * 64,
        factor_ir_hash="b" * 64,
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
        min_observations=2,
        max_constant_ratio=0.9,
        ic_sign=ICSign.ANY,
        min_icir=0.0,
        min_nw_t=0.0,
        quantile_count=3,
        decay_horizons=(5,),
    )


def test_independence_analysis_is_deterministic() -> None:
    candidate = factor(
        FactorObservation("A", at(1), 1.0),
        FactorObservation("B", at(1), 2.0),
        FactorObservation("C", at(1), 3.0),
        FactorObservation("D", at(1), 4.0),
    )
    pool = pool_factor(
        FactorObservation("A", at(1), 2.0),
        FactorObservation("B", at(1), 4.0),
        FactorObservation("C", at(1), 6.0),
        FactorObservation("D", at(1), 8.0),
    )
    series = label(
        LabelObservation("A", at(1), 0.1),
        LabelObservation("B", at(1), 0.2),
        LabelObservation("C", at(1), 0.3),
        LabelObservation("D", at(1), 0.4),
    )

    first = run_independence_analysis(candidate, (pool,), series, policy())
    second = run_independence_analysis(candidate, (pool,), series, policy())

    assert first == second
    assert first.content_hash() == second.content_hash()


def test_identical_factor_replicates_and_loses_incremental_ic() -> None:
    candidate = factor(
        FactorObservation("A", at(1), 1.0),
        FactorObservation("B", at(1), 2.0),
        FactorObservation("C", at(1), 3.0),
        FactorObservation("D", at(1), 4.0),
    )
    pool = pool_factor(
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

    report = run_independence_analysis(candidate, (pool,), series, policy())

    assert report.pairwise[0].pearson == pytest.approx(1.0)
    assert report.replicated_risk_factor is True
    assert report.orthogonalized_ic == pytest.approx(0.0)


def test_orthogonal_factor_keeps_incremental_ic() -> None:
    candidate = factor(
        FactorObservation("A", at(1), 1.0),
        FactorObservation("B", at(1), 1.0),
        FactorObservation("C", at(1), -1.0),
        FactorObservation("D", at(1), -1.0),
    )
    pool = pool_factor(
        FactorObservation("A", at(1), 1.0),
        FactorObservation("B", at(1), -1.0),
        FactorObservation("C", at(1), 1.0),
        FactorObservation("D", at(1), -1.0),
    )
    series = label(
        LabelObservation("A", at(1), 1.0),
        LabelObservation("B", at(1), 1.0),
        LabelObservation("C", at(1), -1.0),
        LabelObservation("D", at(1), -1.0),
    )

    report = run_independence_analysis(candidate, (pool,), series, policy())

    assert report.pairwise[0].pearson == pytest.approx(0.0, abs=1e-9)
    assert report.replicated_risk_factor is False
    assert report.orthogonalized_ic == pytest.approx(1.0)


def test_empty_pool_returns_baseline() -> None:
    candidate = factor(
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

    report = run_independence_analysis(candidate, (), series, policy())

    assert report.pairwise == ()
    assert report.replicated_risk_factor is False
    assert report.orthogonalized_ic == pytest.approx(report.baseline_ic)
