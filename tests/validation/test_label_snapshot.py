from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from quant_platform.validation.contracts import ForwardReturnLabel, LabelSeries
from quant_platform.validation.label_snapshot import (
    FormalLabelSnapshot,
    InMemoryLabelSnapshotCatalog,
    JsonLabelSnapshotCatalog,
    LabelSnapshotRow,
)


def _t(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def label() -> ForwardReturnLabel:
    return ForwardReturnLabel(
        label_id="label://cn-a-fwd-5d/v1",
        market="CN_A",
        horizon=5,
        field_ref="market.eod.fwd_return_5d",
    )


def row(
    instrument_id: str = "600000.SSE", day: int = 1, value: float = 0.2
) -> LabelSnapshotRow:
    event = _t(f"2026-08-0{day}T15:00:00+00:00")
    return LabelSnapshotRow(
        instrument_id=instrument_id,
        event_time=event,
        available_time=event + timedelta(days=7),
        value=value,
    )


def snapshot() -> FormalLabelSnapshot:
    return FormalLabelSnapshot(
        snapshot_id="label-snapshot-cn-a-001",
        label=label(),
        rows=(row(day=1), row(day=2)),
    )


def test_row_requires_available_after_event() -> None:
    event = _t("2026-08-01T15:00:00+00:00")
    with pytest.raises(ValueError):
        LabelSnapshotRow(
            instrument_id="600000.SSE",
            event_time=event,
            available_time=event,
            value=0.2,
        )


def test_row_rejects_non_finite_value() -> None:
    with pytest.raises(ValueError):
        row(value=float("nan"))


def test_snapshot_requires_unique_rows() -> None:
    with pytest.raises(ValueError):
        FormalLabelSnapshot(
            snapshot_id="label-snapshot-cn-a-001",
            label=label(),
            rows=(row(day=1), row(day=1)),
        )


def test_to_label_series_drops_available_time() -> None:
    series = snapshot().to_label_series()

    assert isinstance(series, LabelSeries)
    assert series.label == label()
    assert [obs.value for obs in series.observations] == [0.2, 0.2]


def test_assert_pit_safe_accepts_decision_before_all_available() -> None:
    # earliest available_time is 08-08; a decision on 08-07 is safe.
    snapshot().assert_pit_safe(_t("2026-08-07T15:00:00+00:00"))


def test_assert_pit_safe_rejects_decision_at_or_after_available() -> None:
    # second row is available 08-09; a decision on 08-09 is not safe.
    with pytest.raises(ValueError, match="available at or before decision_time"):
        snapshot().assert_pit_safe(_t("2026-08-09T15:00:00+00:00"))


def test_content_hash_is_deterministic() -> None:
    assert snapshot().content_hash() == snapshot().content_hash()


def test_catalog_resolve_round_trip() -> None:
    snap = snapshot()
    catalog = InMemoryLabelSnapshotCatalog((snap,))

    assert catalog.resolve(snap.snapshot_id, snap.content_hash()) == snap


def test_catalog_rejects_unknown_id() -> None:
    catalog = InMemoryLabelSnapshotCatalog((snapshot(),))

    with pytest.raises(ValueError, match="LABEL_SNAPSHOT_NOT_REGISTERED"):
        catalog.resolve("missing", "0" * 64)


def test_catalog_rejects_hash_mismatch() -> None:
    snap = snapshot()
    catalog = InMemoryLabelSnapshotCatalog((snap,))

    with pytest.raises(ValueError, match="LABEL_SNAPSHOT_MANIFEST_HASH_MISMATCH"):
        catalog.resolve(snap.snapshot_id, "f" * 64)


def test_json_catalog_round_trip(tmp_path: Path) -> None:
    snap = snapshot()
    path = tmp_path / "labels.json"
    path.write_text(json.dumps([snap.payload()]))

    catalog = JsonLabelSnapshotCatalog.from_path(path)

    assert catalog.resolve(snap.snapshot_id, snap.content_hash()) == snap


def test_json_catalog_rejects_unsealed(tmp_path: Path) -> None:
    payload = snapshot().payload()
    payload["sealed"] = False
    path = tmp_path / "labels.json"
    path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="sealed"):
        JsonLabelSnapshotCatalog.from_path(path)


def test_json_catalog_rejects_wrong_artifact_class(tmp_path: Path) -> None:
    payload = snapshot().payload()
    payload["artifact_class"] = "FORMAL"
    path = tmp_path / "labels.json"
    path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="FORMAL_LABEL"):
        JsonLabelSnapshotCatalog.from_path(path)
