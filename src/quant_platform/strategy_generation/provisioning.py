"""按需为策略构建行情数据（G19-P4）。

策略需要的标的/周期缺数据时，不再引导用户换数据，而是直接从 iFinD 拉取
所需数据入库（PIT），让回测/仿真可用。数据源只用 iFinD：

- 日线（1d）：iFinD ``date_sequence``（A 股用股票指标，期货用期货指标）。
- 分钟（5m/15m/30m/60m）：iFinD ``high_frequency``（任意分钟周期、长历史、
  含夜盘；契约 2026-08-24 生产验证）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from quant_platform.data_gateway.ifind_client import (
    IFindClient,
    fetch_futures_daily,
    futures_daily_to_pit_rows,
    hf_to_pit_rows,
    parse_date_sequence,
    parse_high_frequency,
    to_ifind_futures_code,
)
from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.strategy_generation.backtest import (
    _normalize_instrument,
    db_instrument_id,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")

_STOCK_DAILY_INDICATORS = {
    "open": "ths_open_price_stock",
    "high": "ths_high_price_stock",
    "low": "ths_low_stock",
    "close": "ths_close_price_stock",
    "volume": "ths_vol_stock",
}

_DAILY_LOOKBACK_DAYS = 400
_MINUTE_LOOKBACK_DAYS = 90
_HF_INDICATORS = ("open", "high", "low", "close", "volume")


def _interval_minutes(frequency: str) -> int:
    """``5m`` → 5；``15m`` → 15。仅接受分钟级频率。"""
    if not frequency.endswith("m"):
        raise StrategyProvisionError(f"unsupported frequency: {frequency}")
    try:
        minutes = int(frequency[:-1])
    except ValueError as exc:
        raise StrategyProvisionError(f"unsupported frequency: {frequency}") from exc
    if minutes < 1:
        raise StrategyProvisionError(f"unsupported frequency: {frequency}")
    return minutes


def _clamp_eod_end(end: date, *, now: datetime | None = None) -> date:
    """把日线采集窗口终点收敛到最后一个「已可用」的交易日。

    日线 bar 的 available_time 取收盘后 20 分钟（15:20，见
    ``futures_daily_to_pit_rows`` / ``close_series_to_pit_rows``）。若窗口覆盖
    「今天」而当前尚未到 15:20，今天这根 bar 的 available_time 还在未来，会触发
    ``ingested_at < available_time`` 约束。历史回测只应采集已收盘的数据，因此把
    终点收敛到上一交易日（15:20 前）或今天（15:20 后）。
    """
    if now is None:
        now = datetime.now(SHANGHAI)
    if end < now.date():
        return end
    cutoff = now.replace(hour=15, minute=20, second=0, microsecond=0)
    return now.date() if now >= cutoff else now.date() - timedelta(days=1)


class StrategyProvisionError(RuntimeError):
    """Raised when on-demand data provisioning fails."""


@dataclass(frozen=True, slots=True)
class StrategyProvisionResult:
    instrument_ids: tuple[str, ...]
    frequency: str
    rows: int
    sources: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        return {
            "instrument_ids": list(self.instrument_ids),
            "frequency": self.frequency,
            "rows": self.rows,
            "sources": list(self.sources),
        }


def _ifind_client() -> IFindClient:
    token = os.environ.get("IFIND_REFRESH_TOKEN", "").strip()
    if not token:
        raise StrategyProvisionError("IFIND_REFRESH_TOKEN is not configured")
    return IFindClient(refresh_token=token)


def _ifind_stock_code(db_id: str) -> str:
    """库内 ID（600000.SSE）→ iFinD 股票代码（600000.SH）。"""
    symbol, _, suffix = db_id.partition(".")
    return f"{symbol}.{'SH' if suffix == 'SSE' else 'SZ'}"


class StrategyDataProvisioner:
    """为策略草稿按需拉取行情数据并写入 PIT 存储。"""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._store = SqlAlchemyPitStore(sessions)

    def provision(
        self,
        *,
        instrument_ids: tuple[str, ...],
        frequency: str,
        start: date | None = None,
        end: date | None = None,
    ) -> StrategyProvisionResult:
        if frequency not in ("1d", "1w", "5m", "15m", "30m", "60m"):
            raise StrategyProvisionError(f"unsupported frequency: {frequency}")
        if not instrument_ids:
            raise StrategyProvisionError("no instruments to provision")
        # 基础粒度：1d/1w 都拉日线（周线由读取侧聚合）；分钟级统一拉 5m
        # （15/30/60m 由读取侧聚合），iFinD HF 已支持任意分钟区间。
        base_frequency = "1d" if frequency in ("1d", "1w") else "5m"
        end = end or datetime.now(SHANGHAI).date()
        if base_frequency == "1d":
            # 只采已收盘的日线，避免把「今天」尚未可用的 bar 当历史入库。
            end = _clamp_eod_end(end)
        lookback = (
            _DAILY_LOOKBACK_DAYS if base_frequency == "1d" else _MINUTE_LOOKBACK_DAYS
        )
        start = start or (end - timedelta(days=lookback))

        rows: list[RawPITRow] = []
        sources: set[str] = set()
        errors: list[str] = []
        for instrument_id in instrument_ids:
            db_id = db_instrument_id(instrument_id)
            symbol, venue = _normalize_instrument(instrument_id)
            try:
                if base_frequency == "1d":
                    fetched = self._daily(symbol, venue, db_id, start, end)
                else:
                    fetched = self._minute(
                        symbol, venue, db_id, base_frequency, start, end
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{db_id}: {exc}")
                continue
            if not fetched:
                errors.append(f"{db_id}: 数据源未返回任何数据")
                continue
            rows.extend(fetched)
            sources.update(row.source_id for row in fetched)
        if not rows:
            raise StrategyProvisionError("; ".join(errors) or "no data fetched")
        count = self._store.persist(rows)
        return StrategyProvisionResult(
            instrument_ids=tuple(db_instrument_id(item) for item in instrument_ids),
            frequency=frequency,
            rows=count,
            sources=tuple(sorted(sources)),
        )

    def _daily(
        self, symbol: str, venue: str, db_id: str, start: date, end: date
    ) -> list[RawPITRow]:
        client = _ifind_client()
        ingested = datetime.now(UTC)
        if venue in ("SSE", "SZSE"):
            code = _ifind_stock_code(db_id)
            payload = client.fetch_date_sequence(
                (code,),
                tuple(_STOCK_DAILY_INDICATORS.values()),
                start.strftime("%Y-%m-%d"),
                end.strftime("%Y-%m-%d"),
            )
            parsed = parse_date_sequence(payload)
            by_indicator = {
                field: ind for field, ind in _STOCK_DAILY_INDICATORS.items()
            }
            rows: list[RawPITRow] = []
            revision = f"ifind-cn-{ingested.strftime('%Y%m%dT%H%M%S')}"
            for _code, dates in parsed.items():
                for date_str, values in sorted(dates.items()):
                    event_time = datetime.fromisoformat(date_str).replace(
                        hour=15, minute=0, tzinfo=SHANGHAI
                    )
                    for field, indicator in by_indicator.items():
                        value = values.get(indicator)
                        if not isinstance(value, int | float) or float(value) < 0:
                            continue
                        rows.append(
                            RawPITRow(
                                source_id="ifind-cn",
                                dataset_id="market-eod",
                                field=f"market.eod.{field}",
                                instrument_id=db_id,
                                event_time=event_time,
                                available_time=event_time.replace(minute=20),
                                ingested_at=ingested,
                                revision_id=revision,
                                license_tag="formal",
                                value_type="decimal",
                                value=str(value),
                            )
                        )
            return rows
        market_data = fetch_futures_daily(
            client,
            (to_ifind_futures_code(db_id),),
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
        )
        return list(
            futures_daily_to_pit_rows(
                market_data,
                source_id="ifind-cn",
                ingested_at=ingested,
                code_to_db_id={to_ifind_futures_code(db_id): db_id},
            )
        )

    def _minute(
        self,
        symbol: str,
        venue: str,
        db_id: str,
        frequency: str,
        start: date,
        end: date,
    ) -> list[RawPITRow]:
        """分钟线走 iFinD ``high_frequency``（任意分钟周期、长历史、含夜盘）。"""
        client = _ifind_client()
        ifind_code = (
            _ifind_stock_code(db_id)
            if venue in ("SSE", "SZSE")
            else to_ifind_futures_code(db_id)
        )
        payload = client.fetch_high_frequency(
            (ifind_code,),
            _HF_INDICATORS,
            datetime.combine(start, time.min, tzinfo=SHANGHAI).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            datetime.combine(end, time.max, tzinfo=SHANGHAI).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            _interval_minutes(frequency),
        )
        parsed = parse_high_frequency(payload)
        return list(
            hf_to_pit_rows(
                parsed,
                code_to_db_id={ifind_code: db_id},
                field_prefix="market.minute",
                source_id="ifind-cn",
                license_tag="formal",
                ingested_at=datetime.now(UTC),
            )
        )
