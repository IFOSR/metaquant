from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from quant_platform.data_gateway import (
    ArtifactClass,
    ASharePITAdapter,
    DatasetContract,
    FieldContract,
    FrozenSnapshot,
    FuturesContractChainAdapter,
    InMemorySnapshotStore,
    PITDataGateway,
    PITRow,
    QueryPurpose,
    SecurityStatusUnavailableError,
    SourceClass,
)

ROOT = Path(__file__).resolve().parents[2]


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def field(name: str) -> FieldContract:
    return FieldContract(
        name=name,
        value_type="object",
        unit="state",
        license_tag="internal-research",
        allowed_purposes=frozenset({QueryPurpose.RESEARCH, QueryPurpose.BACKTEST}),
    )


def make_gateway() -> PITDataGateway:
    fixture = json.loads(
        (ROOT / "docs" / "golden" / "pit" / "representative.json").read_text()
    )
    contracts = (
        DatasetContract(
            dataset_id="cn_a_master",
            source_id="representative-memory",
            source_class=SourceClass.FORMAL,
            fields=(field("index_membership"), field("security_status")),
        ),
        DatasetContract(
            dataset_id="futures_master",
            source_id="representative-memory",
            source_class=SourceClass.FORMAL,
            fields=(field("actual_contract"),),
        ),
    )
    rows = tuple(
        PITRow(
            dataset_id=item["dataset_id"],
            field=item["field"],
            instrument_id=item["instrument_id"],
            event_time=timestamp(item["event_time"]),
            available_time=timestamp(item["available_time"]),
            ingested_at=timestamp(item["ingested_at"]),
            revision_id=item["revision_id"],
            source_id="representative-memory",
            license_tag="internal-research",
            value=item["value"],
        )
        for item in fixture["rows"]
    )
    snapshot = FrozenSnapshot.create(
        snapshot_id=fixture["snapshot_id"],
        frozen_at=timestamp(fixture["frozen_at"]),
        contracts=contracts,
        rows=rows,
        artifact_class=ArtifactClass.FORMAL,
    )
    return PITDataGateway(InMemorySnapshotStore((snapshot,)))


def test_a_share_adapter_returns_historical_membership_and_status() -> None:
    adapter = ASharePITAdapter(make_gateway())
    access = frozenset({"internal-research"})

    assert adapter.members(
        snapshot_id="pit-representative-v1",
        index_id="000300.CSI",
        trade_date=date(2026, 8, 5),
        decision_time=timestamp("2026-08-05T08:00:00+08:00"),
        purpose=QueryPurpose.BACKTEST,
        allowed_license_tags=access,
    ) == frozenset({"600000.SSE"})
    assert (
        adapter.security_status(
            snapshot_id="pit-representative-v1",
            instrument_id="600000.SSE",
            trade_date=date(2026, 8, 5),
            decision_time=timestamp("2026-08-05T08:00:00+08:00"),
            purpose=QueryPurpose.BACKTEST,
            allowed_license_tags=access,
        )
        == "ST"
    )


def test_futures_adapter_returns_actual_contracts_not_continuous_symbol() -> None:
    adapter = FuturesContractChainAdapter(make_gateway())

    contracts = adapter.actual_contracts(
        snapshot_id="pit-representative-v1",
        product="RB",
        trade_date=date(2026, 8, 5),
        decision_time=timestamp("2026-08-05T08:00:00+08:00"),
        purpose=QueryPurpose.RESEARCH,
        allowed_license_tags=frozenset({"internal-research"}),
    )

    assert [item.instrument_id for item in contracts] == ["RB2610.SHFE"]
    assert all("CONTINUOUS" not in item.instrument_id for item in contracts)


def test_a_share_status_missing_fails_closed() -> None:
    adapter = ASharePITAdapter(make_gateway())

    with pytest.raises(
        SecurityStatusUnavailableError,
        match="no point-in-time security status",
    ):
        adapter.security_status(
            snapshot_id="pit-representative-v1",
            instrument_id="000002.SSE",
            trade_date=date(2026, 8, 5),
            decision_time=timestamp("2026-08-05T08:00:00+08:00"),
            purpose=QueryPurpose.BACKTEST,
            allowed_license_tags=frozenset({"internal-research"}),
        )


def test_a_share_late_status_is_not_treated_as_normal() -> None:
    adapter = ASharePITAdapter(make_gateway())

    with pytest.raises(
        SecurityStatusUnavailableError,
        match="no point-in-time security status",
    ):
        adapter.security_status(
            snapshot_id="pit-representative-v1",
            instrument_id="000001.SSE",
            trade_date=date(2026, 8, 5),
            decision_time=timestamp("2026-08-05T08:00:00+08:00"),
            purpose=QueryPurpose.BACKTEST,
            allowed_license_tags=frozenset({"internal-research"}),
        )

    assert (
        adapter.security_status(
            snapshot_id="pit-representative-v1",
            instrument_id="000001.SSE",
            trade_date=date(2026, 8, 5),
            decision_time=timestamp("2026-08-05T09:30:00+08:00"),
            purpose=QueryPurpose.BACKTEST,
            allowed_license_tags=frozenset({"internal-research"}),
        )
        == "SUSPENDED"
    )
