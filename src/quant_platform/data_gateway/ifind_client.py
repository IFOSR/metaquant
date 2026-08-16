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
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from quant_platform.data_gateway.loader import RawPITRow

if TYPE_CHECKING:
    from quant_platform.data_gateway.resolver import BarRequest, BarSeries

BASE_URL = "https://quantapi.51ifind.com"
SHANGHAI = ZoneInfo("Asia/Shanghai")

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


def close_series_to_pit_rows(
    series: dict[str, dict[str, object]],
    *,
    source_id: str,
    ingested_at: datetime,
    field: str = "market.eod.close",
) -> tuple[RawPITRow, ...]:
    """把 iFinD 不复权收盘价序列转成 FORMAL PIT 行（FR-303）。

    iFinD 的 ``ths_close_price_stock`` 是时点稳定的不复权原始价，可作为
    正式价格数据源进入 PIT 快照。available_time 取收盘后 20 分钟
    （T_CLOSE+20m 的近似）。
    """
    revision = f"{source_id}-{ingested_at.strftime('%Y%m%dT%H%M%S')}"
    rows: list[RawPITRow] = []
    for code, dates in series.items():
        for date_str, close in sorted(dates.items()):
            if not isinstance(close, int | float):
                continue
            event_time = datetime.fromisoformat(date_str).replace(
                hour=15, minute=0, tzinfo=SHANGHAI
            )
            rows.append(
                RawPITRow(
                    source_id=source_id,
                    dataset_id="market-eod",
                    field=field,
                    instrument_id=code,
                    event_time=event_time,
                    available_time=event_time.replace(minute=20),
                    ingested_at=ingested_at,
                    revision_id=revision,
                    license_tag="formal",
                    value_type="decimal",
                    value=str(close),
                )
            )
    return tuple(rows)


class IFindPITAdapter:
    """iFinD 原始价 PIT adapter：拉收盘价序列并转 FORMAL PIT 行。"""

    source_id = "ifind-cn"

    def __init__(
        self,
        client: IFindClient | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client or IFindClient()
        self.clock = clock or (lambda: datetime.now(UTC))

    def fetch(
        self,
        instruments: tuple[str, ...],
        start: date,
        end: date,
        *,
        close_indicator: str = "ths_close_price_stock",
    ) -> tuple[RawPITRow, ...]:
        series = fetch_close_series(
            self.client,
            instruments,
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            close_indicator=close_indicator,
        )
        return close_series_to_pit_rows(
            series,
            source_id=self.source_id,
            ingested_at=self.clock(),
        )


class IFindMarketDataProvider:
    """iFinD-backed provider for the unified bar contract (fallback source).

    Daily bars use ``date_sequence``; minute bars are not yet wired (the
    ``high_frequency`` endpoint exists but its parameter contract still needs
    to be confirmed against the live gateway).
    """

    source_id = "ifind"

    def __init__(self, *, client: IFindClient | None = None) -> None:
        self.client = client or IFindClient()

    def fetch(self, request: BarRequest) -> BarSeries | None:
        from quant_platform.data_gateway.resolver import Bar, BarSeries

        if request.timeframe != "1d":
            return None
        indicator = (
            "ths_close_price_future"
            if request.asset_type == "futures"
            else "ths_close_price_stock"
        )
        try:
            series = fetch_close_series(
                self.client,
                (request.symbol,),
                request.start.strftime("%Y%m%d"),
                request.end.strftime("%Y%m%d"),
                close_indicator=indicator,
            )
        except Exception:
            return None
        per_code = series.get(request.symbol, {})
        bars: list[Bar] = []
        for date_str, close in sorted(per_code.items()):
            if not isinstance(close, int | float):
                continue
            timestamp = datetime.fromisoformat(date_str).replace(
                hour=15, minute=0, tzinfo=SHANGHAI
            )
            value = float(close)
            bars.append(
                Bar(
                    timestamp=timestamp,
                    open=value,
                    high=value,
                    low=value,
                    close=value,
                    volume=0.0,
                )
            )
        if not bars:
            return None
        return BarSeries(request=request, bars=tuple(bars), source_id=self.source_id)
