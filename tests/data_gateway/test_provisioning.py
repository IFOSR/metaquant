"""Tests for on-demand data provisioning (universe + snapshot builders)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.data_gateway.provisioning import (
    build_formal_snapshot,
    build_label_snapshot,
)
from quant_platform.data_gateway.universe import (
    UniverseResolver,
    normalize_czce_code,
)


def test_normalize_czce_code() -> None:
    assert normalize_czce_code("SA2701") == "SA701"
    assert normalize_czce_code("FG2701") == "FG701"
    assert normalize_czce_code("SR2701") == "SR701"
    assert normalize_czce_code("TA2701") == "TA701"


def test_resolve_explicit() -> None:
    spec = UniverseResolver().resolve(
        "futures:explicit",
        explicit=("RB2610.SHF", "AU2612.SHF"),
    )
    assert spec.instruments == ("RB2610.SHF", "AU2612.SHF")
    assert spec.source == "explicit"


def test_resolve_unknown_universe() -> None:
    with pytest.raises(ValueError):
        UniverseResolver().resolve("unknown:thing")


def _row(
    instrument: str, day: int, field: str, value: float
) -> RawPITRow:
    base = datetime(2026, 8, 1, tzinfo=UTC) + timedelta(days=day)
    return RawPITRow(
        source_id="ifind-cn",
        dataset_id="market-eod",
        field=field,
        instrument_id=instrument,
        event_time=base,
        available_time=base + timedelta(minutes=20),
        ingested_at=base + timedelta(hours=1),
        revision_id="ifind-live",
        license_tag="formal",
        value_type="decimal",
        value=str(value),
    )


def _close_series(instrument: str, closes: tuple[float, ...]) -> tuple[RawPITRow, ...]:
    return tuple(
        _row(instrument, day, "market.eod.close", value)
        for day, value in enumerate(closes)
    )


def test_build_label_snapshot_alignment() -> None:
    # 两个合约，各 10 天收盘价；前 9 天递增，第 10 天用来算未来收益
    rows: list[RawPITRow] = []
    for instrument in ("A.SHF", "B.SHF"):
        rows.extend(
            _close_series(
                instrument,
                tuple(100.0 + i * 10 for i in range(12)),
            )
        )
    label, decision_time = build_label_snapshot(rows, snapshot_id="label-x", horizon=2)

    assert label["snapshot_id"] == "label-x"
    assert label["artifact_class"] == "FORMAL_LABEL"
    label_rows = label["rows"]
    assert isinstance(label_rows, list) and label_rows
    # 决策时点在数据末尾前 2*horizon 个交易日，label 只覆盖其前 horizon 天
    assert len({row["event_time"] for row in label_rows}) <= 2
    # 未来 2 日收益：第一个 valid 时点（close=170）的未来收益 = (190-170)/170
    first = label_rows[0]
    assert first["value"] == pytest.approx(20 / 170)


def test_build_formal_snapshot_metadata() -> None:
    rows = list(_close_series("A.SHF", (100.0, 110.0, 120.0)))
    snapshot = build_formal_snapshot(
        rows, snapshot_id="snap-x", universe_ref="futures:liquid-initial"
    )
    assert snapshot["snapshot_id"] == "snap-x"
    assert snapshot["sealed"] is True
    assert snapshot["artifact_class"] == "FORMAL"
    assert snapshot["universe_ref"] == "futures:liquid-initial"
    assert len(snapshot["rows"]) == 3
