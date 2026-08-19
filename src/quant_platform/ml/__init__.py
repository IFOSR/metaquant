"""Sandbox data client (shipped inside the sandbox image, not the control plane).

The generated ``train.py`` / ``infer.py`` import only this package. It has no
database access and no label capability in the feature loader: features come
back PIT-safe from the read-only data service, and labels come only through
``load_label_frame`` (a separate call the training script makes explicitly).

Only stdlib + pandas/numpy are used so the sandbox image stays lean.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, cast

import pandas as pd


@dataclass(frozen=True)
class PITFrame:
    """A point-in-time frame indexed by ``(instrument_id, event_time)``."""

    data: pd.DataFrame
    decision_time: str

    def __post_init__(self) -> None:
        if not isinstance(self.data.index, pd.MultiIndex):
            raise ValueError("PITFrame must be indexed by (instrument_id, event_time)")
        if self.data.index.has_duplicates:
            raise ValueError("PITFrame index must be unique (instrument, event_time)")


def _rows_to_frame(rows: list[dict[str, Any]], fields: list[str]) -> pd.DataFrame:
    if not rows:
        return (
            pd.DataFrame(columns=fields)
            .assign(
                instrument_id=pd.Series(dtype="object"),
                event_time=pd.Series(dtype="object"),
            )
            .set_index(["instrument_id", "event_time"])
        )
    df = pd.DataFrame(rows)
    df = df.set_index(["instrument_id", "event_time"])
    return df[[column for column in fields if column in df.columns]]


def _base(base_url: str | None) -> str:
    return (base_url or os.environ.get("ML_DATA_SERVICE_URL", "") or "").rstrip("/")


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    url = f"{_base(base_url)}{path}"
    if params:
        from urllib.parse import urlencode

        url += "?" + urlencode(params)
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=payload, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {os.environ.get('ML_DATA_TOKEN', '')}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return cast(dict[str, Any], json.loads(response.read().decode()))


def load_pit_frame(
    *,
    snapshot_id: str,
    instrument_ids: list[str],
    fields: list[str],
    decision_time: str,
    field_prefix: str = "market.eod.",
    base_url: str | None = None,
) -> PITFrame:
    """Load a PIT-safe feature frame (no label column, no future rows)."""
    del snapshot_id  # reserved for universe resolution; instrument_ids are concrete
    response = _request(
        "GET",
        "/v1/data/pit-frame",
        params={
            "instrument_ids": ",".join(instrument_ids),
            "fields": ",".join(fields),
            "decision_time": decision_time,
            "field_prefix": field_prefix,
        },
        base_url=base_url,
    )
    frame = _rows_to_frame(response.get("rows", []), fields)
    return PITFrame(data=frame, decision_time=decision_time)


def load_label_frame(
    *,
    snapshot_id: str,
    instrument_ids: list[str],
    price_field: str,
    horizon: int,
    decision_time: str,
    return_type: str = "simple",
    field_prefix: str = "market.eod.",
    base_url: str | None = None,
) -> pd.Series:
    """Load forward-return labels (training only; requires a training grant)."""
    del snapshot_id
    response = _request(
        "POST",
        "/v1/data/label-frame",
        body={
            "instrument_ids": instrument_ids,
            "price_field": price_field,
            "horizon": horizon,
            "decision_time": decision_time,
            "return_type": return_type,
            "field_prefix": field_prefix,
        },
        base_url=base_url,
    )
    rows = response.get("rows", [])
    if not rows:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(rows).set_index(["instrument_id", "event_time"])
    return df["label"].astype(float)


def load_exposure_frame(
    *,
    snapshot_id: str,
    instrument_ids: list[str],
    factors: list[str],
    decision_time: str,
    base_url: str | None = None,
) -> pd.DataFrame:
    """Load style exposures (size/volatility/reversal/liquidity) for neutralization."""
    del snapshot_id
    response = _request(
        "GET",
        "/v1/data/pit-frame",
        params={
            "instrument_ids": ",".join(instrument_ids),
            "fields": ",".join(factors),
            "decision_time": decision_time,
            "field_prefix": "style.",
        },
        base_url=base_url,
    )
    return _rows_to_frame(response.get("rows", []), factors)
