from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.experiments import FactorComputationArtifact, FactorObservation
from quant_platform.validation.turnover import FactorSeries, run_turnover


def at(day: int) -> datetime:
    return datetime(2026, 8, day, 15, tzinfo=UTC)


def section(day: int, *observations: FactorObservation) -> FactorComputationArtifact:
    return FactorComputationArtifact.create(
        artifact_id=f"artifact-{day}",
        run_id="run-001",
        attempt_id="attempt-001",
        experiment_spec_hash="1" * 64,
        factor_ir_hash="a" * 64,
        snapshot_id="snapshot-001",
        snapshot_manifest_hash="3" * 64,
        input_hash="4" * 64,
        observations=observations,
    )


def constant_sections(days: tuple[int, ...]) -> FactorSeries:
    return FactorSeries(
        tuple(
            section(
                day,
                FactorObservation("A", at(day), 1.0),
                FactorObservation("B", at(day), 2.0),
                FactorObservation("C", at(day), 3.0),
                FactorObservation("D", at(day), 4.0),
            )
            for day in days
        )
    )


def test_factor_series_requires_at_least_two_cross_sections() -> None:
    with pytest.raises(ValueError):
        FactorSeries((section(1, FactorObservation("A", at(1), 1.0)),))


def test_factor_series_rejects_unordered_cross_sections() -> None:
    with pytest.raises(ValueError):
        FactorSeries(
            (
                section(2, FactorObservation("A", at(2), 1.0)),
                section(1, FactorObservation("A", at(1), 1.0)),
            )
        )


def test_constant_factor_has_zero_turnover() -> None:
    series = constant_sections((1, 2, 3))

    report = run_turnover(series)

    assert report.raw_turnover == 0.0
    assert report.buffered_turnover == 0.0
    assert report.period_count == 3
    assert report.signal_half_life is None


def test_reversed_factor_has_positive_turnover() -> None:
    series = FactorSeries(
        (
            section(
                1,
                FactorObservation("A", at(1), 1.0),
                FactorObservation("B", at(1), 2.0),
                FactorObservation("C", at(1), 3.0),
                FactorObservation("D", at(1), 4.0),
            ),
            section(
                2,
                FactorObservation("A", at(2), 4.0),
                FactorObservation("B", at(2), 3.0),
                FactorObservation("C", at(2), 2.0),
                FactorObservation("D", at(2), 1.0),
            ),
        )
    )

    report = run_turnover(series)

    assert report.raw_turnover == pytest.approx(0.4)
    assert report.buffered_turnover > 0.0


def test_run_turnover_is_deterministic() -> None:
    series = constant_sections((1, 2, 3))

    first = run_turnover(series)
    second = run_turnover(series)

    assert first == second
    assert first.content_hash() == second.content_hash()
