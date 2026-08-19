"""PIT-safety tests for the read-only data service."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.data_gateway.models import PITRow
from quant_platform.factor_construction.data_service import (
    forward_returns,
    pivot_frame,
    visible_pit_rows,
)


def _t(day: int) -> datetime:
    return datetime(2026, 8, day, 7, 0, tzinfo=UTC)


def row(
    field: str,
    instrument_id: str,
    value: float,
    *,
    event_time: datetime,
    available_time: datetime | None = None,
    ingested_at: datetime | None = None,
) -> PITRow:
    avail = available_time or event_time
    ingest = ingested_at or avail
    return PITRow(
        dataset_id="market",
        field=field,
        instrument_id=instrument_id,
        event_time=event_time,
        available_time=avail,
        ingested_at=ingest,
        revision_id="rev-1",
        source_id="ifind-cn",
        license_tag="licensed-research",
        value=value,
    )


def test_visible_pit_rows_drops_future_available() -> None:
    decision = _t(10)
    rows = (
        row("market.eod.close", "A", 1.0, event_time=_t(9), available_time=_t(9)),
        row("market.eod.close", "B", 2.0, event_time=_t(9), available_time=_t(11)),
    )
    visible = visible_pit_rows(rows, decision_time=decision)
    assert [r.instrument_id for r in visible] == ["A"]


def test_visible_pit_rows_drops_future_ingested() -> None:
    decision = _t(10)
    rows = (
        row(
            "market.eod.close",
            "A",
            1.0,
            event_time=_t(9),
            available_time=_t(9),
            ingested_at=_t(9),
        ),
        row(
            "market.eod.close",
            "B",
            2.0,
            event_time=_t(9),
            available_time=_t(9),
            ingested_at=_t(12),
        ),
    )
    visible = visible_pit_rows(rows, decision_time=decision)
    assert [r.instrument_id for r in visible] == ["A"]


def test_visible_pit_rows_keeps_at_decision_time() -> None:
    decision = _t(10)
    rows = (row("market.eod.close", "A", 1.0, event_time=_t(9), available_time=_t(10)),)
    assert len(visible_pit_rows(rows, decision_time=decision)) == 1


def test_pivot_frame_maps_short_fields() -> None:
    rows = (
        row("market.eod.close", "A", 10.0, event_time=_t(1)),
        row("market.eod.open", "A", 9.0, event_time=_t(1)),
        row("market.eod.close", "B", 20.0, event_time=_t(1)),
    )
    frame = pivot_frame(rows, fields=("close", "open"))
    by_key = {(r["instrument_id"], r["event_time"]): r for r in frame["rows"]}
    assert by_key[("A", "2026-08-01T07:00:00Z")]["close"] == 10.0
    assert by_key[("A", "2026-08-01T07:00:00Z")]["open"] == 9.0


def test_forward_returns_computes_label() -> None:
    prices = [100.0, 101.0, 103.0, 106.0]
    rows = tuple(
        row("market.eod.vwap", "A", p, event_time=_t(1 + i))
        for i, p in enumerate(prices)
    )
    labels = forward_returns(rows, price_field="market.eod.vwap", horizon=2)
    # label[i] = price[i+2]/price[i] - 1
    expected = [0.03, 106 / 101 - 1]  # only i=0,1 have i+2 within range
    assert [r["label"] for r in labels["rows"]] == pytest.approx(expected)


def test_forward_returns_log_type() -> None:
    import math

    rows = tuple(
        row("market.eod.vwap", "A", p, event_time=_t(1 + i))
        for i, p in enumerate([100.0, 100.0, 110.0])
    )
    labels = forward_returns(
        rows, price_field="market.eod.vwap", horizon=2, return_type="log"
    )
    assert labels["rows"][0]["label"] == pytest.approx(math.log(1.1))
