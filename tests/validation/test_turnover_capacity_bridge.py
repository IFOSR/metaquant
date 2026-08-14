from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.data_gateway.models import (
    ArtifactClass,
    DatasetContract,
    FieldContract,
    FrozenSnapshot,
    PITRow,
    QueryPurpose,
    SourceClass,
)
from quant_platform.experiments import FactorComputationArtifact, FactorObservation
from quant_platform.validation.capacity import (
    CapacityModel,
    extract_tradability,
    run_capacity,
)
from quant_platform.validation.turnover import build_factor_series, run_turnover


def at(day: int) -> datetime:
    return datetime(2026, 8, day, 15, tzinfo=UTC)


def multi_period_factor() -> FactorComputationArtifact:
    return FactorComputationArtifact.create(
        artifact_id="artifact-multi",
        run_id="run-001",
        attempt_id="attempt-001",
        experiment_spec_hash="1" * 64,
        factor_ir_hash="a" * 64,
        snapshot_id="snapshot-001",
        snapshot_manifest_hash="3" * 64,
        input_hash="4" * 64,
        observations=(
            FactorObservation("A", at(1), 1.0),
            FactorObservation("B", at(1), 2.0),
            FactorObservation("A", at(2), 3.0),
            FactorObservation("B", at(2), 4.0),
            FactorObservation("A", at(3), 5.0),
            FactorObservation("B", at(3), 6.0),
        ),
    )


def snapshot_with_market_data() -> FrozenSnapshot:
    contract = DatasetContract(
        dataset_id="market-eod",
        source_id="licensed-source",
        source_class=SourceClass.FORMAL,
        fields=(
            FieldContract(
                "market.eod.adv",
                "decimal",
                "CNY",
                "licensed-research",
                frozenset({QueryPurpose.RESEARCH}),
            ),
            FieldContract(
                "market.eod.tradable",
                "boolean",
                "1",
                "licensed-research",
                frozenset({QueryPurpose.RESEARCH}),
            ),
        ),
    )
    rows = (
        PITRow(
            "market-eod",
            "market.eod.adv",
            "A",
            at(1),
            at(1),
            at(1),
            "r1",
            "licensed-source",
            "licensed-research",
            1_000_000.0,
        ),
        PITRow(
            "market-eod",
            "market.eod.tradable",
            "A",
            at(1),
            at(1),
            at(1),
            "r1",
            "licensed-source",
            "licensed-research",
            True,
        ),
        PITRow(
            "market-eod",
            "market.eod.adv",
            "B",
            at(1),
            at(1),
            at(1),
            "r1",
            "licensed-source",
            "licensed-research",
            500_000.0,
        ),
        PITRow(
            "market-eod",
            "market.eod.tradable",
            "B",
            at(1),
            at(1),
            at(1),
            "r1",
            "licensed-source",
            "licensed-research",
            False,
        ),
    )
    return FrozenSnapshot.create(
        snapshot_id="snapshot-market-001",
        frozen_at=at(2),
        contracts=(contract,),
        rows=rows,
        artifact_class=ArtifactClass.FORMAL,
    )


def test_build_factor_series_splits_periods() -> None:
    series = build_factor_series(multi_period_factor())

    assert series.cross_sections and len(series.cross_sections) == 3
    assert all(len(cs.observations) == 2 for cs in series.cross_sections)


def test_build_factor_series_preserves_values() -> None:
    series = build_factor_series(multi_period_factor())

    first = series.cross_sections[0].observations
    assert {obs.instrument_id: obs.value for obs in first} == {"A": 1.0, "B": 2.0}
    last = series.cross_sections[-1].observations
    assert {obs.instrument_id: obs.value for obs in last} == {"A": 5.0, "B": 6.0}


def test_build_factor_series_rejects_single_period() -> None:
    single = FactorComputationArtifact.create(
        artifact_id="artifact-single",
        run_id="run-001",
        attempt_id="attempt-001",
        experiment_spec_hash="1" * 64,
        factor_ir_hash="a" * 64,
        snapshot_id="snapshot-001",
        snapshot_manifest_hash="3" * 64,
        input_hash="4" * 64,
        observations=(
            FactorObservation("A", at(1), 1.0),
            FactorObservation("B", at(1), 2.0),
        ),
    )

    with pytest.raises(ValueError):
        build_factor_series(single)


def test_build_then_run_turnover_end_to_end() -> None:
    series = build_factor_series(multi_period_factor())

    report = run_turnover(series)

    # constant cross-sectional ranks -> zero buffered turnover
    assert report.period_count == 3
    assert report.buffered_turnover == 0.0


def test_extract_adv_and_tradable() -> None:
    adv, tradable = extract_tradability(snapshot_with_market_data())

    assert adv == {"A": 1_000_000.0, "B": 500_000.0}
    assert tradable == {"A": True, "B": False}


def test_extract_skips_nonpositive_adv() -> None:
    snapshot = snapshot_with_market_data()
    # a third instrument with negative ADV must be skipped
    rows = snapshot.rows + (
        PITRow(
            "market-eod",
            "market.eod.adv",
            "C",
            at(1),
            at(1),
            at(1),
            "r1",
            "licensed-source",
            "licensed-research",
            -100.0,
        ),
    )
    frozen = FrozenSnapshot.create(
        snapshot_id="snapshot-market-002",
        frozen_at=at(2),
        contracts=tuple(snapshot.contracts.values()),
        rows=rows,
        artifact_class=ArtifactClass.FORMAL,
    )

    adv, _ = extract_tradability(frozen)

    assert "C" not in adv


def test_extract_then_run_capacity_end_to_end() -> None:
    adv, tradable = extract_tradability(snapshot_with_market_data())
    model = CapacityModel(
        market="CN_A",
        max_adv_participation=0.1,
        impact_coefficient=0.5,
        margin_rate=1.0,
        exclude_limit_up_down=True,
        exclude_suspended=True,
    )

    report = run_capacity(adv, tradable, model)

    # only A is tradable, so total capacity = A.adv * participation
    assert report.tradable_count == 1
    assert report.total_capacity == pytest.approx(1_000_000.0 * 0.1)
