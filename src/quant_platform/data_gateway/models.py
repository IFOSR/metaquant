from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from types import MappingProxyType


class QueryPurpose(str, Enum):
    RESEARCH = "RESEARCH"
    DERIVED_FACTOR = "DERIVED_FACTOR"
    BACKTEST = "BACKTEST"
    REPORT = "REPORT"
    PAPER = "PAPER"
    LIVE = "LIVE"


class SourceClass(str, Enum):
    FORMAL = "FORMAL"
    OFFICIAL = "OFFICIAL"
    EXPLORATORY = "EXPLORATORY"

    @property
    def is_formal(self) -> bool:
        return self is not SourceClass.EXPLORATORY


class ArtifactClass(str, Enum):
    FORMAL = "FORMAL"
    EXPLORATORY = "EXPLORATORY"


def _require_identifier(value: str, label: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{label} must be a non-empty normalized identifier")


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class FieldContract:
    name: str
    value_type: str
    unit: str
    license_tag: str
    allowed_purposes: frozenset[QueryPurpose]

    def __post_init__(self) -> None:
        _require_identifier(self.name, "field name")
        _require_identifier(self.value_type, "value_type")
        _require_identifier(self.unit, "unit")
        _require_identifier(self.license_tag, "license_tag")
        if not self.allowed_purposes:
            raise ValueError("allowed_purposes must not be empty")

    def assert_access(
        self,
        purpose: QueryPurpose,
        allowed_license_tags: frozenset[str],
    ) -> None:
        if purpose not in self.allowed_purposes:
            raise PermissionError(
                f"field {self.name} does not allow purpose {purpose.value}"
            )
        if self.license_tag not in allowed_license_tags:
            raise PermissionError(
                f"field {self.name} requires license tag {self.license_tag}"
            )


@dataclass(frozen=True, slots=True)
class DatasetContract:
    dataset_id: str
    source_id: str
    source_class: SourceClass
    fields: tuple[FieldContract, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.dataset_id, "dataset_id")
        _require_identifier(self.source_id, "source_id")
        if not self.fields:
            raise ValueError("fields must not be empty")
        names = tuple(item.name for item in self.fields)
        if len(set(names)) != len(names):
            raise ValueError("field names must be unique")

    def field(self, name: str) -> FieldContract:
        for item in self.fields:
            if item.name == name:
                return item
        raise KeyError(f"field {name} is not declared by dataset {self.dataset_id}")

    def assert_formal(self) -> None:
        if not self.source_class.is_formal:
            raise PermissionError("exploratory source cannot be queried formally")


@dataclass(frozen=True, slots=True)
class PITRow:
    dataset_id: str
    field: str
    instrument_id: str
    event_time: datetime
    available_time: datetime
    ingested_at: datetime
    revision_id: str
    source_id: str
    license_tag: str
    value: object

    def __post_init__(self) -> None:
        _require_identifier(self.dataset_id, "dataset_id")
        _require_identifier(self.field, "field")
        _require_identifier(self.instrument_id, "instrument_id")
        _require_aware(self.event_time, "event_time")
        _require_aware(self.available_time, "available_time")
        _require_aware(self.ingested_at, "ingested_at")
        _require_identifier(self.revision_id, "revision_id")
        _require_identifier(self.source_id, "source_id")
        _require_identifier(self.license_tag, "license_tag")
        if self.ingested_at < self.available_time:
            raise ValueError("ingested_at must not precede available_time")
        object.__setattr__(self, "value", _freeze(self.value))

    @property
    def revision_key(self) -> tuple[str, str, str, datetime]:
        return (
            self.dataset_id,
            self.field,
            self.instrument_id,
            self.event_time,
        )


@dataclass(frozen=True, slots=True)
class FrozenSnapshot:
    snapshot_id: str
    frozen_at: datetime
    artifact_class: ArtifactClass
    contracts: Mapping[str, DatasetContract]
    rows: tuple[PITRow, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.snapshot_id, "snapshot_id")
        if self.snapshot_id.lower() == "latest":
            raise ValueError("snapshot_id must identify an immutable version")
        _require_aware(self.frozen_at, "frozen_at")

        contracts = dict(self.contracts)
        if not contracts:
            raise ValueError("snapshot contracts must not be empty")
        object.__setattr__(self, "contracts", MappingProxyType(contracts))
        object.__setattr__(self, "rows", tuple(self.rows))

        for item in self.rows:
            try:
                contract = contracts[item.dataset_id]
            except KeyError as exc:
                raise ValueError(
                    f"row references undeclared dataset {item.dataset_id}"
                ) from exc
            field = contract.field(item.field)
            if item.source_id != contract.source_id:
                raise ValueError("row source_id does not match dataset contract")
            if item.license_tag != field.license_tag:
                raise ValueError("row license_tag does not match field contract")
            if item.ingested_at > self.frozen_at:
                raise ValueError("snapshot contains a row ingested after frozen_at")

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        frozen_at: datetime,
        contracts: tuple[DatasetContract, ...],
        rows: tuple[PITRow, ...],
        artifact_class: ArtifactClass,
    ) -> FrozenSnapshot:
        by_id = {item.dataset_id: item for item in contracts}
        if len(by_id) != len(contracts):
            raise ValueError("dataset_id values must be unique within a snapshot")
        return cls(
            snapshot_id=snapshot_id,
            frozen_at=frozen_at,
            artifact_class=artifact_class,
            contracts=by_id,
            rows=rows,
        )


@dataclass(frozen=True, slots=True)
class SnapshotQuery:
    snapshot_id: str
    dataset_id: str
    fields: tuple[str, ...]
    decision_time: datetime
    purpose: QueryPurpose
    allowed_license_tags: frozenset[str]

    def __post_init__(self) -> None:
        _require_identifier(self.snapshot_id, "snapshot_id")
        if self.snapshot_id.lower() == "latest":
            raise ValueError("formal query requires an explicit snapshot_id")
        _require_identifier(self.dataset_id, "dataset_id")
        if not self.fields or len(set(self.fields)) != len(self.fields):
            raise ValueError("fields must be non-empty and unique")
        for name in self.fields:
            _require_identifier(name, "field")
        _require_aware(self.decision_time, "decision_time")
        if not self.allowed_license_tags:
            raise PermissionError("formal query requires allowed license tags")


@dataclass(frozen=True, slots=True)
class SnapshotSlice:
    snapshot_id: str
    dataset_id: str
    decision_time: datetime
    purpose: QueryPurpose
    rows: tuple[PITRow, ...]


@dataclass(frozen=True, slots=True)
class ActualFuturesContract:
    instrument_id: str
    product: str
    exchange: str
    listed_on: date
    last_trade_date: date
