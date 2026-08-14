from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.data_gateway.loader import (
    CrossValidationStatus,
    MarketDataSource,
    RawPITRow,
    filter_and_resolve,
    validate_pit_rows,
)
from quant_platform.data_gateway.vendor import (
    VendorSourceClass,
    exploratory_response,
    formal_response,
    guard_exploratory,
)


def at(day: int, hour: int = 15) -> datetime:
    return datetime(2026, 8, day, hour, tzinfo=UTC)


def row(
    field: str = "market.eod.close",
    event_time: datetime | None = None,
    available_time: datetime | None = None,
    ingested_at: datetime | None = None,
    revision_id: str = "r1",
    value: str = "10",
) -> RawPITRow:
    event = event_time or at(1)
    return RawPITRow(
        source_id="vendor-a",
        dataset_id="market-eod",
        field=field,
        instrument_id="600000.SSE",
        event_time=event,
        available_time=available_time or event,
        ingested_at=ingested_at or event,
        revision_id=revision_id,
        license_tag="licensed-research",
        value_type="decimal",
        value=value,
    )


def test_data_source_registration() -> None:
    source = MarketDataSource(
        source_id="vendor-a",
        name="Vendor A",
        license="lic-2026-001",
        coverage_scope="CN_A equities",
        revision_capable=True,
        pit_capable=True,
        cross_validation_status=CrossValidationStatus.PENDING,
    )

    assert source.payload()["pit_capable"] is True
    assert source.cross_validation_status is CrossValidationStatus.PENDING


def test_raw_row_rejects_future_leaking_availability() -> None:
    with pytest.raises(ValueError, match="available_time"):
        row(available_time=at(1, 10), event_time=at(1, 15))


def test_validate_pit_rows_rejects_duplicates() -> None:
    first = row()
    duplicate = row()
    with pytest.raises(ValueError, match="duplicate"):
        validate_pit_rows((first, duplicate))


def test_filter_and_resolve_drops_future_rows() -> None:
    visible = row(event_time=at(1), available_time=at(1, 15))
    future = row(event_time=at(3), available_time=at(3, 15))
    decision_time = at(2, 16)

    resolved = filter_and_resolve((visible, future), decision_time=decision_time)

    assert resolved == (visible,)


def test_filter_and_resolve_keeps_latest_revision() -> None:
    original = row(ingested_at=at(1, 15), revision_id="r1", value="10")
    revision = row(ingested_at=at(1, 16), revision_id="r2", value="11")

    resolved = filter_and_resolve((original, revision), decision_time=at(2, 16))

    assert len(resolved) == 1
    assert resolved[0].revision_id == "r2"
    assert resolved[0].value == "11"


def test_filter_and_resolve_hides_late_revision() -> None:
    # The revised value arrived after the decision time, so the original row
    # must survive (PIT revision resolution).
    original = row(ingested_at=at(1, 15), revision_id="r1", value="10")
    late_revision = row(ingested_at=at(3, 15), revision_id="r2", value="99")

    resolved = filter_and_resolve((original, late_revision), decision_time=at(2, 16))

    assert resolved == (original,)


def test_exploratory_rows_are_blocked_from_formal_contexts() -> None:
    response = exploratory_response((row(),))

    assert response.source_class is VendorSourceClass.EXPLORATORY
    assert response.formal_rows() == ()
    with pytest.raises(ValueError, match="EXPLORATORY_SOURCE_REJECTED"):
        guard_exploratory(response, "formal validation")


def test_formal_rows_pass_guard() -> None:
    response = formal_response((row(),))

    assert response.formal_rows() == (row(),)
    guard_exploratory(response, "formal validation")
