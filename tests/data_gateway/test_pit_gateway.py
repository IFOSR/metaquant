from __future__ import annotations

from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import cast

import pytest

from quant_platform.data_gateway import (
    ArtifactClass,
    DatasetContract,
    FieldContract,
    FrozenSnapshot,
    InMemorySnapshotStore,
    PITDataGateway,
    PITRow,
    QueryPurpose,
    SnapshotQuery,
    SourceClass,
)


def at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, tzinfo=UTC)


def contract(
    *,
    purposes: frozenset[QueryPurpose] = frozenset(
        {QueryPurpose.RESEARCH, QueryPurpose.BACKTEST}
    ),
    source_class: SourceClass = SourceClass.FORMAL,
) -> DatasetContract:
    return DatasetContract(
        dataset_id="fundamentals",
        source_id="licensed-source",
        source_class=source_class,
        fields=(
            FieldContract(
                name="revenue",
                value_type="decimal",
                unit="CNY",
                license_tag="internal-research",
                allowed_purposes=purposes,
            ),
            FieldContract(
                name="future_sentinel",
                value_type="string",
                unit="sentinel",
                license_tag="internal-research",
                allowed_purposes=purposes,
            ),
        ),
    )


def row(
    revision_id: str,
    available_time: datetime,
    value: object,
    *,
    field: str = "revenue",
    instrument_id: str = "600000.SSE",
) -> PITRow:
    return PITRow(
        dataset_id="fundamentals",
        field=field,
        instrument_id=instrument_id,
        event_time=at(1),
        available_time=available_time,
        ingested_at=available_time,
        revision_id=revision_id,
        source_id="licensed-source",
        license_tag="internal-research",
        value=value,
    )


def gateway_for(
    rows: tuple[PITRow, ...],
    *,
    dataset_contract: DatasetContract | None = None,
    artifact_class: ArtifactClass = ArtifactClass.FORMAL,
    snapshot_id: str = "snapshot-001",
) -> PITDataGateway:
    snapshot = FrozenSnapshot.create(
        snapshot_id=snapshot_id,
        frozen_at=at(10),
        contracts=(dataset_contract or contract(),),
        rows=rows,
        artifact_class=artifact_class,
    )
    return PITDataGateway(InMemorySnapshotStore((snapshot,)))


def query(
    decision_time: datetime,
    *,
    purpose: QueryPurpose = QueryPurpose.RESEARCH,
    fields: tuple[str, ...] = ("revenue",),
    snapshot_id: str = "snapshot-001",
    license_tags: frozenset[str] = frozenset({"internal-research"}),
) -> SnapshotQuery:
    return SnapshotQuery(
        snapshot_id=snapshot_id,
        dataset_id="fundamentals",
        fields=fields,
        decision_time=decision_time,
        purpose=purpose,
        allowed_license_tags=license_tags,
    )


def test_field_contract_and_pit_row_require_complete_normalized_metadata() -> None:
    with pytest.raises(ValueError, match="unit"):
        FieldContract(
            name="revenue",
            value_type="decimal",
            unit="",
            license_tag="internal-research",
            allowed_purposes=frozenset({QueryPurpose.RESEARCH}),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        PITRow(
            dataset_id="fundamentals",
            field="revenue",
            instrument_id="600000.SSE",
            event_time=datetime(2026, 8, 1),
            available_time=at(2),
            ingested_at=at(2),
            revision_id="r1",
            source_id="licensed-source",
            license_tag="internal-research",
            value=1,
        )


def test_pit_row_recursively_freezes_mapping_and_sequence_values() -> None:
    flags = ["SPECIAL_TREATMENT"]
    source: dict[str, object] = {"status": "ST", "flags": flags}

    item = row("r1", at(2), source)
    source["status"] = "NORMAL"
    flags.append("FUTURE")

    frozen = cast(MutableMapping[str, object], item.value)
    assert frozen["status"] == "ST"
    assert frozen["flags"] == ("SPECIAL_TREATMENT",)
    with pytest.raises(TypeError):
        frozen["status"] = "DELISTED"


def test_query_only_reads_an_explicit_frozen_snapshot() -> None:
    gateway = gateway_for((row("r1", at(2), 100),))

    with pytest.raises(ValueError, match="explicit snapshot_id"):
        query(at(3), snapshot_id="latest")
    with pytest.raises(KeyError, match="unknown frozen snapshot"):
        gateway.query(query(at(3), snapshot_id="missing"))


def test_available_time_and_revision_selection_are_hard_gateway_constraints() -> None:
    gateway = gateway_for(
        (
            row("r1", at(2), 100),
            row("r2", at(4), 110),
            row("r3", at(8), 999),
        )
    )

    result = gateway.query(query(at(5)))

    assert [(item.revision_id, item.value) for item in result.rows] == [("r2", 110)]
    assert all(item.available_time <= at(5) for item in result.rows)


def test_license_and_purpose_are_enforced_before_rows_are_returned() -> None:
    gateway = gateway_for((row("r1", at(2), 100),))

    with pytest.raises(PermissionError, match="license tag"):
        gateway.query(query(at(3), license_tags=frozenset({"report-only"})))
    with pytest.raises(PermissionError, match="purpose"):
        gateway.query(query(at(3), purpose=QueryPurpose.LIVE))


def test_exploratory_contract_or_artifact_cannot_enter_formal_query() -> None:
    exploratory_contract = contract(source_class=SourceClass.EXPLORATORY)
    contract_gateway = gateway_for(
        (row("r1", at(2), 100),),
        dataset_contract=exploratory_contract,
    )
    artifact_gateway = gateway_for(
        (row("r1", at(2), 100),),
        artifact_class=ArtifactClass.EXPLORATORY,
    )

    with pytest.raises(PermissionError, match="exploratory source"):
        contract_gateway.query(query(at(3)))
    with pytest.raises(PermissionError, match="EXPLORATORY artifact"):
        artifact_gateway.query(query(at(3)))


def test_future_truncation_and_future_sentinel_do_not_change_history() -> None:
    historical = (
        row("r1", at(2), 100),
        row("r2", at(4), 110),
    )
    baseline = gateway_for(historical).query(query(at(5)))
    contaminated = gateway_for(
        historical
        + (
            row("future-revision", at(9), -999_999),
            row(
                "future-sentinel",
                at(3),
                "LEAK",
                field="future_sentinel",
            ),
        )
    ).query(query(at(5)))

    assert contaminated.rows == baseline.rows
