from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType


class FactorExecutionError(ValueError):
    pass


def _timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("factor input values must be numeric or null")
    result = float(value)
    return result if math.isfinite(result) else None


@dataclass(frozen=True, slots=True)
class FactorInputRow:
    timestamp: datetime
    instrument_id: str
    values: Mapping[str, float | None]

    def __post_init__(self) -> None:
        if not self.instrument_id or self.instrument_id.strip() != self.instrument_id:
            raise ValueError("instrument_id must be normalized")
        normalized: dict[str, float | None] = {}
        for name, value in self.values.items():
            if not name or name.strip() != name:
                raise ValueError("input column names must be normalized")
            normalized[name] = _number(value)
        object.__setattr__(self, "timestamp", _timestamp(self.timestamp))
        object.__setattr__(self, "values", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class FactorTable:
    rows: tuple[FactorInputRow, ...]

    def __post_init__(self) -> None:
        rows = tuple(
            sorted(self.rows, key=lambda item: (item.timestamp, item.instrument_id))
        )
        keys = [(item.timestamp, item.instrument_id) for item in rows]
        if len(set(keys)) != len(keys):
            raise ValueError("factor table row keys must be unique")
        object.__setattr__(self, "rows", rows)


@dataclass(frozen=True, slots=True)
class FactorObservation:
    timestamp: datetime
    instrument_id: str
    value: float | None


@dataclass(frozen=True, slots=True)
class FactorExecutionResult:
    factor_id: str
    ir_hash: str
    observations: tuple[FactorObservation, ...]
    canonical_json: str
    output_hash: str


def canonical_observations(
    rows: Iterable[FactorInputRow | FactorObservation],
    value_name: str,
) -> tuple[str, str]:
    if not value_name or value_name.strip() != value_name:
        raise ValueError("value_name must be normalized")
    observations = []
    for row in sorted(rows, key=lambda item: (item.timestamp, item.instrument_id)):
        if isinstance(row, FactorInputRow):
            if value_name not in row.values:
                raise FactorExecutionError(f"missing input {value_name}")
            value = row.values[value_name]
        else:
            value = row.value
        observations.append(
            {
                "instrument_id": row.instrument_id,
                "timestamp": row.timestamp.astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "value": 0.0 if value == 0 else value,
            }
        )
    payload = {
        "observations": observations,
        "schema_version": "factor-observations/v1",
        "value_name": value_name,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()
