"""Sealed label snapshot contracts (G5-001).

A ``FormalLabelSnapshot`` is a sealed formal snapshot dedicated to forward-return
labels. Each row carries an ``available_time`` strictly after its ``event_time``
(the return realizes only later), so the label's PIT safety is a property of the
sealed snapshot rather than a client-supplied timestamp.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

from quant_platform.experiments import canonical_hash
from quant_platform.validation.contracts import (
    ForwardReturnLabel,
    LabelObservation,
    LabelSeries,
    _require_aware,
    _require_identifier,
)


@dataclass(frozen=True, slots=True)
class LabelSnapshotRow:
    instrument_id: str
    event_time: datetime
    available_time: datetime
    value: float | None

    def __post_init__(self) -> None:
        _require_identifier(self.instrument_id, "instrument_id")
        _require_aware(self.event_time, "event_time")
        _require_aware(self.available_time, "available_time")
        if self.available_time <= self.event_time:
            raise ValueError("label available_time must be strictly after event_time")
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("label value must be finite or None")


@dataclass(frozen=True, slots=True)
class FormalLabelSnapshot:
    snapshot_id: str
    label: ForwardReturnLabel
    rows: tuple[LabelSnapshotRow, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.snapshot_id, "snapshot_id")
        keys = [(item.instrument_id, item.event_time) for item in self.rows]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "label snapshot rows must be unique per instrument and time"
            )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> FormalLabelSnapshot:
        label_payload = cast(dict[str, Any], payload["label"])
        label = ForwardReturnLabel(
            label_id=str(label_payload["label_id"]),
            market=str(label_payload["market"]),
            horizon=int(label_payload["horizon"]),
            field_ref=str(label_payload["field_ref"]),
            return_definition=str(
                label_payload.get("return_definition", "close_to_close")
            ),
        )
        rows = tuple(
            LabelSnapshotRow(
                instrument_id=str(row["instrument_id"]),
                event_time=datetime.fromisoformat(str(row["event_time"])),
                available_time=datetime.fromisoformat(str(row["available_time"])),
                value=float(row["value"]) if row.get("value") is not None else None,
            )
            for row in cast(list[dict[str, Any]], payload["rows"])
        )
        return cls(snapshot_id=str(payload["snapshot_id"]), label=label, rows=rows)

    def to_label_series(self) -> LabelSeries:
        return LabelSeries(
            label=self.label,
            observations=tuple(
                LabelObservation(item.instrument_id, item.event_time, item.value)
                for item in self.rows
            ),
        )

    def assert_pit_safe(self, decision_time: datetime) -> None:
        """Require every label row to be unavailable at the decision time.

        The forward-return label for a factor decided at ``decision_time``
        realizes its return only later, so each row's ``available_time`` must be
        strictly after ``decision_time``. This is the sealed-snapshot analogue of
        ``assert_label_pit_safe`` and keeps labels out of factor computation.
        """
        _require_aware(decision_time, "decision_time")
        for row in self.rows:
            if row.available_time <= decision_time:
                raise ValueError(
                    "label row "
                    f"{row.instrument_id}@{row.event_time.isoformat()} "
                    "is available at or before decision_time"
                )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "label-snapshot/v1",
            "snapshot_id": self.snapshot_id,
            "sealed": True,
            "artifact_class": "FORMAL_LABEL",
            "label": {
                "label_id": self.label.label_id,
                "market": self.label.market,
                "horizon": self.label.horizon,
                "field_ref": self.label.field_ref,
                "return_definition": self.label.return_definition,
            },
            "rows": [
                {
                    "instrument_id": item.instrument_id,
                    "event_time": item.event_time.isoformat(),
                    "available_time": item.available_time.isoformat(),
                    "value": item.value,
                }
                for item in self.rows
            ],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


class LabelSnapshotCatalog(Protocol):
    def resolve(self, snapshot_id: str, manifest_hash: str) -> FormalLabelSnapshot: ...
    def register(self, snapshot: FormalLabelSnapshot) -> None: ...


class InMemoryLabelSnapshotCatalog:
    def __init__(self, snapshots: tuple[FormalLabelSnapshot, ...]) -> None:
        self._snapshots = {str(item.snapshot_id): item for item in snapshots}
        if len(self._snapshots) != len(snapshots):
            raise ValueError("label snapshot ids must be unique")

    def resolve(self, snapshot_id: str, manifest_hash: str) -> FormalLabelSnapshot:
        try:
            snapshot = self._snapshots[snapshot_id]
        except KeyError as exc:
            raise ValueError("LABEL_SNAPSHOT_NOT_REGISTERED") from exc
        if snapshot.content_hash() != manifest_hash:
            raise ValueError("LABEL_SNAPSHOT_MANIFEST_HASH_MISMATCH")
        return snapshot

    def register(self, snapshot: FormalLabelSnapshot) -> None:
        """运行时注册一个密封 label 快照（按需数据供给用）。"""
        self._snapshots[str(snapshot.snapshot_id)] = snapshot


class JsonLabelSnapshotCatalog(InMemoryLabelSnapshotCatalog):
    @classmethod
    def from_path(cls, path: Path) -> JsonLabelSnapshotCatalog:
        document = json.loads(path.read_text())
        if not isinstance(document, list):
            raise ValueError("label snapshot catalog must be a JSON array")
        snapshots: list[FormalLabelSnapshot] = []
        for item in cast(list[dict[str, Any]], document):
            if item.get("sealed") is not True:
                raise ValueError("label snapshot catalog accepts only sealed snapshots")
            if item.get("artifact_class") != "FORMAL_LABEL":
                raise ValueError(
                    "label snapshot catalog accepts only FORMAL_LABEL snapshots"
                )
            label_payload = cast(dict[str, Any], item["label"])
            label = ForwardReturnLabel(
                label_id=str(label_payload["label_id"]),
                market=str(label_payload["market"]),
                horizon=int(label_payload["horizon"]),
                field_ref=str(label_payload["field_ref"]),
                return_definition=str(
                    label_payload.get("return_definition", "close_to_close")
                ),
            )
            rows = tuple(
                LabelSnapshotRow(
                    instrument_id=str(row["instrument_id"]),
                    event_time=datetime.fromisoformat(str(row["event_time"])),
                    available_time=datetime.fromisoformat(str(row["available_time"])),
                    value=(
                        float(row["value"]) if row.get("value") is not None else None
                    ),
                )
                for row in cast(list[dict[str, Any]], item["rows"])
            )
            snapshots.append(
                FormalLabelSnapshot(
                    snapshot_id=str(item["snapshot_id"]),
                    label=label,
                    rows=rows,
                )
            )
        return cls(tuple(snapshots))
