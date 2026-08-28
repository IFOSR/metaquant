"""Contract tests for the sandbox data client (quant_platform.ml)."""

from __future__ import annotations

from typing import Any

import pytest

import quant_platform.ml as ml
from quant_platform.ml import PITFrame, _rows_to_frame


def test_rows_to_frame_sets_multi_index() -> None:
    frame = _rows_to_frame(
        [
            {"instrument_id": "A", "event_time": "2026-08-01T07:00:00Z", "close": 1.0},
            {"instrument_id": "B", "event_time": "2026-08-01T07:00:00Z", "close": 2.0},
        ],
        fields=["close", "open"],
    )
    assert list(frame.index.names) == ["instrument_id", "event_time"]
    assert frame.loc[("A", "2026-08-01T07:00:00Z"), "close"] == 1.0


def test_pitframe_rejects_duplicate_index() -> None:
    import pandas as pd

    data = pd.DataFrame(
        {
            "instrument_id": ["A", "A"],
            "event_time": ["t", "t"],
            "close": [1.0, 2.0],
        }
    ).set_index(["instrument_id", "event_time"])
    with pytest.raises(ValueError):
        PITFrame(data=data, decision_time="t")


def test_load_pit_frame_has_no_label_column(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(
        method: str,
        path: str,
        *,
        params: Any = None,
        body: Any = None,
        base_url: Any = None,
    ) -> Any:
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params
        return {
            "rows": [
                {
                    "instrument_id": "A",
                    "event_time": "2026-08-01T07:00:00Z",
                    "close": 1.0,
                }
            ]
        }

    monkeypatch.setattr(ml, "_request", fake_request)
    frame = ml.load_pit_frame(
        snapshot_id="snap",
        instrument_ids=["A"],
        fields=["close"],
        decision_time="2026-08-01T07:00:00Z",
        base_url="http://data",
    )
    assert captured["path"] == "/v1/data/pit-frame"
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["decision_time"] == "2026-08-01T07:00:00Z"
    assert "label" not in frame.data.columns
    assert list(frame.data.index.names) == ["instrument_id", "event_time"]


def test_load_label_frame_returns_series(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(
        method: str,
        path: str,
        *,
        params: Any = None,
        body: Any = None,
        base_url: Any = None,
    ) -> Any:
        return {
            "rows": [
                {
                    "instrument_id": "A",
                    "event_time": "2026-08-01T07:00:00Z",
                    "label": 0.03,
                }
            ]
        }

    monkeypatch.setattr(ml, "_request", fake_request)
    labels = ml.load_label_frame(
        snapshot_id="snap",
        instrument_ids=["A"],
        price_field="vwap",
        horizon=21,
        decision_time="2026-08-01T07:00:00Z",
    )
    assert labels.loc[("A", "2026-08-01T07:00:00Z")] == 0.03


def test_load_exposure_frame_uses_style_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(
        method: str,
        path: str,
        *,
        params: Any = None,
        body: Any = None,
        base_url: Any = None,
    ) -> Any:
        captured["params"] = params
        return {"rows": []}

    monkeypatch.setattr(ml, "_request", fake_request)
    ml.load_exposure_frame(
        snapshot_id="snap",
        instrument_ids=["A"],
        factors=["size", "volatility"],
        decision_time="2026-08-01T07:00:00Z",
    )
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["field_prefix"] == "style."
