"""AkShare-backed market data vendor adapter (G16-009, FR-303/306).

Borrows the timeout-isolated call, column validation, and numeric/date
normalization patterns from the open AkShare provider. AkShare exposes
current-availability daily bars rather than point-in-time revisions, so this
adapter's rows are always tagged ``EXPLORATORY`` and can never enter formal
gates, strategy packages, or live trading (FR-312).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time
from queue import Queue
from threading import Thread
from typing import Any
from zoneinfo import ZoneInfo

from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.data_gateway.resolver import Bar, BarRequest, BarSeries
from quant_platform.data_gateway.vendor import (
    VendorResponse,
    VendorSourceClass,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


class AkShareVendorAdapter:
    source_id = "akshare-cn"
    source_class = VendorSourceClass.EXPLORATORY
    name = "akshare"

    def __init__(
        self,
        *,
        module: Any | None = None,
        timeout_seconds: float = 10.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.module = module
        self.timeout_seconds = timeout_seconds
        self.clock = clock or (lambda: datetime.now(UTC))

    def _call(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Invoke an AkShare function with a hard timeout (borrowed pattern)."""
        result: Queue[tuple[bool, Any]] = Queue(maxsize=1)

        def invoke() -> None:
            try:
                result.put((True, function(*args, **kwargs)))
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                result.put((False, exc))

        thread = Thread(target=invoke, daemon=True)
        thread.start()
        thread.join(self.timeout_seconds)
        if thread.is_alive():
            raise TimeoutError("AkShare market data timed out")
        succeeded, value = result.get_nowait()
        if succeeded:
            return value
        if isinstance(value, BaseException):
            raise value
        raise RuntimeError("AkShare call failed without an exception")

    def _module(self) -> Any:
        if self.module is None:
            import akshare

            self.module = akshare
        return self.module

    @staticmethod
    def _required_columns(frame: Any, fields: set[str]) -> None:
        missing = sorted(fields - set(frame.columns))
        if missing:
            raise ValueError(
                "AkShare response missing required columns: " + ", ".join(missing)
            )

    def fetch(
        self,
        instruments: tuple[str, ...],
        start: date,
        end: date,
    ) -> VendorResponse:
        """Fetch daily bars for A-share or futures symbols via AkShare.

        ``instruments`` are AkShare symbols (e.g. ``RB2510`` for a futures
        contract, ``600000`` for an A-share). Each daily close becomes one
        PIT row per field.
        """
        module = self._module()
        ingested = self.clock()
        rows: list[RawPITRow] = []
        for symbol in instruments:
            frame = self._daily_frame(module, symbol, start, end)
            if frame is None or frame.empty:
                continue
            rows.extend(self._to_rows(symbol, frame, ingested))
        return VendorResponse(
            source_class=VendorSourceClass.EXPLORATORY, rows=tuple(rows)
        )

    def _daily_frame(self, module: Any, symbol: str, start: date, end: date) -> Any:
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        try:
            if symbol.isdigit() and len(symbol) <= 6:
                return self._call(
                    module.stock_zh_a_hist,
                    symbol=symbol,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                    adjust="",
                )
            return self._call(
                module.futures_zh_daily_sina,
                symbol=symbol,
            )
        except Exception:  # noqa: BLE001 - a failed fetch yields no rows
            return None

    def _to_rows(self, symbol: str, frame: Any, ingested: datetime) -> list[RawPITRow]:
        self._required_columns(frame, {"date", "close"})
        rows: list[RawPITRow] = []
        revision = f"akshare-{ingested.strftime('%Y%m%dT%H%M%S')}"
        for _, record in frame.iterrows():
            trade_date = _date(record["date"])
            close = _number(record.get("close"))
            if trade_date is None or close is None:
                continue
            event_time = datetime.combine(trade_date, time(15, 0), tzinfo=SHANGHAI)
            rows.append(
                RawPITRow(
                    source_id=self.source_id,
                    dataset_id="market-eod",
                    field="market.eod.close",
                    instrument_id=symbol,
                    event_time=event_time,
                    available_time=event_time.replace(minute=30),
                    ingested_at=ingested,
                    revision_id=revision,
                    license_tag="exploratory",
                    value_type="decimal",
                    value=str(close),
                )
            )
        return rows


def _date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _number(value: object) -> float | None:
    import math

    try:
        result = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class AkShareMarketDataProvider:
    """AkShare-backed provider for the unified bar contract (futures first).

    Futures minute bars come from ``futures_zh_minute_sina`` (includes night
    sessions), futures daily bars from ``futures_zh_daily_sina``, and stock
    bars from ``stock_zh_a_minute`` / ``stock_zh_a_hist``.
    """

    source_id = "akshare"

    def __init__(self, *, module: Any | None = None) -> None:
        self.module = module

    def _ak(self) -> Any:
        if self.module is None:
            import akshare as ak  # noqa: PLC0415

            self.module = ak
        return self.module

    def fetch(self, request: BarRequest) -> BarSeries | None:
        ak = self._ak()
        frame = self._fetch_frame(ak, request)
        if frame is None or getattr(frame, "empty", True):
            return None
        bars = self._to_bars(frame)
        if not bars:
            return None
        return BarSeries(request=request, bars=tuple(bars), source_id=self.source_id)

    def _fetch_frame(self, ak: Any, request: BarRequest) -> Any:
        period = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60"}.get(
            request.timeframe
        )
        if request.asset_type == "futures":
            if request.timeframe == "1d":
                return ak.futures_zh_daily_sina(symbol=request.symbol)
            return ak.futures_zh_minute_sina(symbol=request.symbol, period=period)
        if request.timeframe == "1d":
            return ak.stock_zh_a_hist(
                symbol=request.symbol,
                period="daily",
                start_date=request.start.strftime("%Y%m%d"),
                end_date=request.end.strftime("%Y%m%d"),
                adjust="",
            )
        sina_symbol = request.symbol
        if not request.symbol.startswith(("sh", "sz", "bj")):
            sina_symbol = (
                "sh" + request.symbol
                if request.symbol.startswith(("6", "9"))
                else "sz" + request.symbol
            )
        return ak.stock_zh_a_minute(symbol=sina_symbol, period=period, adjust="")

    def _to_bars(self, frame: Any) -> list[Bar]:
        columns = set(frame.columns)
        time_col = "datetime" if "datetime" in columns else "day"
        if time_col not in columns:
            time_col = "日期" if "日期" in columns else "date"
        bars: list[Bar] = []
        for _, row in frame.iterrows():
            timestamp = _parse_bar_time(row[time_col])
            raw_values = {
                "open": _number(row.get("open", row.get("开盘"))),
                "high": _number(row.get("high", row.get("最高"))),
                "low": _number(row.get("low", row.get("最低"))),
                "close": _number(row.get("close", row.get("收盘"))),
                "volume": _number(row.get("volume", row.get("成交量"))),
            }
            o_value = raw_values["open"]
            h_value = raw_values["high"]
            l_value = raw_values["low"]
            c_value = raw_values["close"]
            v_value = raw_values["volume"]
            if timestamp is None:
                continue
            if (
                o_value is None
                or h_value is None
                or l_value is None
                or c_value is None
                or v_value is None
            ):
                continue
            extra: dict[str, float] = {}
            for key, name in (
                ("hold", "持仓量"),
                ("settle", "settle"),
                ("amount", "成交额"),
            ):
                candidate = _number(row.get(key, row.get(name)))
                if candidate is not None:
                    extra[key] = candidate
            bars.append(
                Bar(
                    timestamp=timestamp,
                    open=float(o_value),
                    high=float(h_value),
                    low=float(l_value),
                    close=float(c_value),
                    volume=float(v_value),
                    extra=extra,
                )
            )
        return bars


def _parse_bar_time(value: object) -> datetime | None:
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        result = to_pydatetime()
        return result.replace(tzinfo=SHANGHAI) if isinstance(result, datetime) else None
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or SHANGHAI)
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=SHANGHAI)
    except ValueError:
        return None
