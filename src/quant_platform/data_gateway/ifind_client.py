"""同花顺 iFinD HTTP API client (G17, FR-303/306).

Talks to the quantapi.51ifind.com HTTP gateway directly (no local SDK), so it
works without the ``iFinDPy`` package. The refresh token is long-lived and is
exchanged for a 7-day access token, which is then used to fetch daily bars and
date sequences.

Endpoints (confirmed against the live gateway):

- ``POST /api/v1/get_access_token``  body ``{"refresh_token": "..."}``
- ``POST /api/v1/basic_data_service`` header ``access_token``
- ``POST /api/v1/date_sequence``       header ``access_token``
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable

BASE_URL = "https://quantapi.51ifind.com"

HttpPost = Callable[[str, dict[str, object], dict[str, str]], dict[str, object]]


def _http_post(
    path: str, body: dict[str, object], headers: dict[str, str]
) -> dict[str, object]:
    request = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "ifindlang": "cn",
            **headers,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"iFinD HTTP {exc.code} on {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("iFinD response is not a JSON object")
    return payload


def _require_zero(payload: dict[str, object], operation: str) -> None:
    code = payload.get("errorcode", payload.get("errcode"))
    if code not in (0, "0"):
        raise RuntimeError(f"iFinD {operation} failed: {payload.get('errmsg', code)}")


class IFindClient:
    def __init__(
        self,
        refresh_token: str | None = None,
        *,
        post: HttpPost = _http_post,
        access_token: str | None = None,
    ) -> None:
        if not refresh_token and not access_token:
            refresh_token = os.environ.get("IFIND_REFRESH_TOKEN")
        if not refresh_token and not access_token:
            raise ValueError(
                "refresh_token or access_token is required; set IFIND_REFRESH_TOKEN"
            )
        self.refresh_token = refresh_token
        self._access_token = access_token
        self._post = post

    def get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        assert self.refresh_token is not None
        payload = self._post(
            "/api/v1/get_access_token",
            {"refresh_token": self.refresh_token},
            {},
        )
        _require_zero(payload, "get_access_token")
        token = payload.get("access_token") or payload.get("accessToken")
        if not isinstance(token, str) or not token:
            data = payload.get("data")
            if isinstance(data, dict):
                token = data.get("access_token") or data.get("accessToken")
        if not isinstance(token, str) or not token:
            raise RuntimeError("get_access_token returned no access_token")
        self._access_token = token
        return token

    def _auth_headers(self) -> dict[str, str]:
        return {"access_token": self.get_access_token()}

    def fetch_daily_bars(
        self,
        codes: tuple[str, ...],
        indicators: tuple[str, ...],
        start_date: str,
        end_date: str,
    ) -> dict[str, object]:
        """Fetch daily bars via ``basic_data_service`` (FR-303/306).

        ``indicators`` are iFinD indicator ids such as ``ths_close_price_stock``
        or ``ths_open_price_stock``; ``start_date``/``end_date`` are ``YYYYMMDD``.
        """
        if not codes or not indicators:
            raise ValueError("codes and indicators must not be empty")
        body: dict[str, object] = {
            "codes": ",".join(codes),
            "indipara": [
                {"indicator": indicator, "indiparams": [start_date, "100", end_date]}
                for indicator in indicators
            ],
        }
        payload = self._post("/api/v1/basic_data_service", body, self._auth_headers())
        _require_zero(payload, "basic_data_service")
        return payload

    def fetch_date_sequence(
        self,
        codes: tuple[str, ...],
        indicators: tuple[str, ...],
        start_date: str,
        end_date: str,
    ) -> dict[str, object]:
        """Fetch a date-indexed sequence via ``date_sequence``."""
        if not codes or not indicators:
            raise ValueError("codes and indicators must not be empty")
        body: dict[str, object] = {
            "codes": ",".join(codes),
            "startdate": start_date,
            "enddate": end_date,
            "functionpara": {"Days": "Alldays", "Fill": "-1"},
            "indipara": [
                {"indicator": indicator, "indiparams": ["", "100"]}
                for indicator in indicators
            ],
        }
        payload = self._post("/api/v1/date_sequence", body, self._auth_headers())
        _require_zero(payload, "date_sequence")
        return payload


def parse_date_sequence(
    payload: dict[str, object],
) -> dict[str, dict[str, dict[str, object]]]:
    """Parse a ``date_sequence`` response into ``{code: {date: {indicator: value}}}``.

    The live gateway returns ``tables[].time`` (date strings) and
    ``tables[].table`` (indicator id to a value list aligned with time).
    """
    tables = payload.get("tables")
    if not isinstance(tables, list):
        return {}
    result: dict[str, dict[str, dict[str, object]]] = {}
    for entry in tables:
        if not isinstance(entry, dict):
            continue
        code = entry.get("thscode")
        times = entry.get("time")
        table = entry.get("table")
        if not isinstance(code, str) or not isinstance(times, list):
            continue
        if not isinstance(table, dict):
            continue
        series: dict[str, dict[str, object]] = {}
        for indicator, values in table.items():
            if not isinstance(values, list):
                continue
            for index, date_str in enumerate(times):
                if index >= len(values):
                    break
                if not isinstance(date_str, str):
                    continue
                series.setdefault(date_str, {})[indicator] = values[index]
        result[code] = series
    return result


def fetch_close_series(
    client: IFindClient,
    codes: tuple[str, ...],
    start_date: str,
    end_date: str,
    *,
    close_indicator: str = "ths_close_price_stock",
) -> dict[str, dict[str, object]]:
    """Fetch a close-price series per code as ``{code: {date: close}}``."""
    payload = client.fetch_date_sequence(
        codes, (close_indicator,), start_date, end_date
    )
    parsed = parse_date_sequence(payload)
    return {
        code: {
            date_str: values[close_indicator]
            for date_str, values in series.items()
            if close_indicator in values
        }
        for code, series in parsed.items()
    }


def load_client_from_env() -> IFindClient:
    return IFindClient()
