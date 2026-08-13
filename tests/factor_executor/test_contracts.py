from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from quant_platform.factor_executor import (
    FactorInputRow,
    FactorTable,
    canonical_observations,
)


def at(day: int, *, tz: timezone = UTC) -> datetime:
    return datetime(2026, 8, day, 15, tzinfo=tz)


def test_factor_table_is_sorted_immutable_and_normalizes_non_finite_values() -> None:
    values = {"close": float("inf"), "volume": 10}
    table = FactorTable(
        rows=(
            FactorInputRow(
                timestamp=at(2),
                instrument_id="600000.SSE",
                values=values,
            ),
            FactorInputRow(
                timestamp=at(1, tz=timezone(timedelta(hours=8))),
                instrument_id="000001.SZSE",
                values={"close": 12.5, "volume": None},
            ),
        )
    )
    values["close"] = 99

    assert [row.instrument_id for row in table.rows] == [
        "000001.SZSE",
        "600000.SSE",
    ]
    assert table.rows[0].timestamp == datetime(2026, 8, 1, 7, tzinfo=UTC)
    assert table.rows[1].values["close"] is None
    with pytest.raises(TypeError):
        table.rows[0].values["close"] = 0  # type: ignore[index]


def test_factor_table_rejects_duplicate_keys_and_invalid_cell_types() -> None:
    row = FactorInputRow(
        timestamp=at(1),
        instrument_id="RB2610.SHFE",
        values={"settlement": 3500.0},
    )
    with pytest.raises(ValueError, match="unique"):
        FactorTable(rows=(row, row))
    with pytest.raises(TypeError, match="numeric or null"):
        FactorInputRow(
            timestamp=at(1),
            instrument_id="RB2610.SHFE",
            values={"settlement": True},
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        FactorInputRow(
            timestamp=datetime(2026, 8, 1),
            instrument_id="RB2610.SHFE",
            values={"settlement": 3500.0},
        )


def test_canonical_observations_are_order_independent_and_json_safe() -> None:
    rows = (
        FactorInputRow(at(2), "600000.SSE", {"factor": -0.0}),
        FactorInputRow(at(1), "000001.SZSE", {"factor": None}),
    )

    canonical_json, output_hash = canonical_observations(reversed(rows), "factor")

    assert json.loads(canonical_json) == {
        "observations": [
            {
                "instrument_id": "000001.SZSE",
                "timestamp": "2026-08-01T15:00:00Z",
                "value": None,
            },
            {
                "instrument_id": "600000.SSE",
                "timestamp": "2026-08-02T15:00:00Z",
                "value": 0.0,
            },
        ],
        "schema_version": "factor-observations/v1",
        "value_name": "factor",
    }
    assert len(output_hash) == 64
    assert canonical_observations(rows, "factor") == (canonical_json, output_hash)
