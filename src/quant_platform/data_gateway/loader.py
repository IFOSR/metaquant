"""Market data loader contracts (G16-006, FR-301/FR-311).

Registers formal data sources with their license, coverage, revision, and PIT
capabilities, and validates raw vendor rows into sealed PIT observations that
satisfy the field-level contract (event time, available time, ingested time,
revision id).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class CrossValidationStatus(StrEnum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class MarketDataSource:
    source_id: str
    name: str
    license: str
    coverage_scope: str
    revision_capable: bool
    pit_capable: bool
    cross_validation_status: CrossValidationStatus

    def __post_init__(self) -> None:
        if not self.source_id or self.source_id.strip() != self.source_id:
            raise ValueError("source_id must be a non-empty normalized identifier")
        for label, value in (
            ("name", self.name),
            ("license", self.license),
            ("coverage_scope", self.coverage_scope),
        ):
            if not value:
                raise ValueError(f"{label} must not be empty")
        if not isinstance(self.cross_validation_status, CrossValidationStatus):
            object.__setattr__(
                self,
                "cross_validation_status",
                CrossValidationStatus(self.cross_validation_status),
            )

    def payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "license": self.license,
            "coverage_scope": self.coverage_scope,
            "revision_capable": self.revision_capable,
            "pit_capable": self.pit_capable,
            "cross_validation_status": self.cross_validation_status.value,
        }


@dataclass(frozen=True, slots=True)
class RawPITRow:
    """A vendor row normalized to the platform's PIT field contract (FR-301)."""

    source_id: str
    dataset_id: str
    field: str
    instrument_id: str
    event_time: datetime
    available_time: datetime
    ingested_at: datetime
    revision_id: str
    license_tag: str
    value_type: str
    value: str

    def __post_init__(self) -> None:
        for label, value in (
            ("source_id", self.source_id),
            ("dataset_id", self.dataset_id),
            ("field", self.field),
            ("instrument_id", self.instrument_id),
            ("revision_id", self.revision_id),
            ("license_tag", self.license_tag),
            ("value_type", self.value_type),
            ("value", self.value),
        ):
            if not value or value.strip() != value:
                raise ValueError(f"{label} must be a non-empty normalized identifier")
        if self.available_time < self.event_time:
            raise ValueError("available_time must not precede event_time")
        if self.ingested_at < self.available_time:
            raise ValueError("ingested_at must not precede available_time")


def validate_pit_rows(rows: Sequence[RawPITRow]) -> None:
    """Validate a batch of raw rows before loading.

    Rejects future-leaking availability (available before event) and duplicate
    observation keys, which would make revision resolution ambiguous.
    """
    keys: set[tuple[str, str, datetime]] = set()
    for row in rows:
        key = (row.field, row.instrument_id, row.event_time)
        if key in keys:
            raise ValueError("duplicate observation key")
        keys.add(key)


def filter_and_resolve(
    rows: tuple[RawPITRow, ...],
    *,
    decision_time: datetime,
) -> tuple[RawPITRow, ...]:
    """Filter to rows visible at ``decision_time`` and resolve revisions.

    Only rows whose available time is at or before the decision time survive;
    among surviving revisions of the same (field, instrument, event_time) key,
    the latest ingested revision wins (PIT revision resolution).
    """
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("decision_time must be timezone-aware")
    visible = tuple(
        row
        for row in rows
        if row.available_time <= decision_time and row.ingested_at <= decision_time
    )
    latest: dict[tuple[str, str, datetime], RawPITRow] = {}
    for row in visible:
        key = (row.field, row.instrument_id, row.event_time)
        existing = latest.get(key)
        if existing is None or row.ingested_at > existing.ingested_at:
            latest[key] = row
    return tuple(
        latest[key] for key in sorted(latest, key=lambda item: (item[0], item[1]))
    )


def utc_now() -> datetime:
    return datetime.now(UTC)
