"""真实行情采集入库（G18 数据接入：iFinD / AkShare → pit_observations）。

用法（在 api 容器内）：
    python scripts/ingest-market-data.py \
        --instruments RB2610.SHF,AU2612.SHF \
        --start 2025-08-01 --end 2026-08-15 \
        --freq 1d,5m --source auto

- ``--source auto``：配置了 ``IFIND_REFRESH_TOKEN`` 走 iFinD（FORMAL），
  否则回退 AkShare（EXPLORATORY，研究级，不进正式门禁）
- 日线：iFinD 全字段（OHLC/量/持仓/结算）或 AkShare 日线（OHLCV）
- 分钟线：AkShare ``futures_zh_minute_sina``；iFinD 分钟接口契约未验证，暂不接
"""

from __future__ import annotations

import argparse
import os
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from quant_platform.data_gateway.ifind_client import (
    IFindClient,
    fetch_futures_daily,
    futures_daily_to_pit_rows,
)
from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.data_gateway.resolver import Bar, BarRequest

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _sina_symbol(instrument_id: str) -> str:
    return instrument_id.partition(".")[0]


def _ifind_daily(instruments: tuple[str, ...], start: date, end: date) -> tuple[RawPITRow, ...]:
    client = IFindClient(refresh_token=os.environ["IFIND_REFRESH_TOKEN"])
    market_data = fetch_futures_daily(
        client, instruments, start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    )
    return futures_daily_to_pit_rows(
        market_data, source_id="ifind-cn", ingested_at=datetime.now(UTC)
    )


def _bars_to_pit_rows(
    bars: tuple[Bar, ...],
    *,
    instrument_id: str,
    field_prefix: str,
    source_id: str,
    license_tag: str,
    ingested: datetime,
) -> list[RawPITRow]:
    revision = f"{source_id}-{ingested.strftime('%Y%m%dT%H%M%S')}"
    rows: list[RawPITRow] = []
    for bar in bars:
        timestamp = bar.timestamp
        if field_prefix == "market.eod":
            # 日线统一对齐到平台 EOD 约定：T 日 15:00（与 iFinD/封存快照一致），
            # 否则同一交易日会出现两套 bar。
            timestamp = timestamp.replace(hour=15, minute=0, second=0)
        values = {
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for field, value in values.items():
            rows.append(
                RawPITRow(
                    source_id=source_id,
                    dataset_id="market-eod" if field_prefix == "market.eod" else "market-minute",
                    field=f"{field_prefix}.{field}",
                    instrument_id=instrument_id,
                    event_time=timestamp,
                    available_time=timestamp,
                    ingested_at=ingested,
                    revision_id=revision,
                    license_tag=license_tag,
                    value_type="decimal",
                    value=str(value),
                )
            )
    return rows


def _akshare_bars(
    instruments: tuple[str, ...], start: date, end: date, timeframe: str
) -> list[RawPITRow]:
    from quant_platform.data_gateway.akshare_vendor import AkShareMarketDataProvider

    provider = AkShareMarketDataProvider()
    ingested = datetime.now(UTC)
    rows: list[RawPITRow] = []
    for instrument in instruments:
        series = provider.fetch(
            BarRequest(
                asset_type="futures",
                symbol=_sina_symbol(instrument),
                timeframe=timeframe,
                start=datetime.combine(start, time.min, tzinfo=SHANGHAI),
                end=datetime.combine(end, time.max, tzinfo=SHANGHAI),
            )
        )
        if series is None:
            print(f"  [警告] {instrument} {timeframe} 无数据")
            continue
        prefix = "market.eod" if timeframe == "1d" else "market.minute"
        rows.extend(
            _bars_to_pit_rows(
                series.bars,
                instrument_id=instrument,
                field_prefix=prefix,
                source_id="akshare-cn",
                license_tag="exploratory",
                ingested=ingested,
            )
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="真实行情采集入库")
    parser.add_argument("--instruments", required=True, help="逗号分隔，如 RB2610.SHF,AU2612.SHF")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--freq", default="1d", help="1d 或 1d,5m")
    parser.add_argument("--source", default="auto", choices=["auto", "ifind", "akshare"])
    args = parser.parse_args()

    instruments = tuple(item.strip() for item in args.instruments.split(",") if item.strip())
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    freqs = [item.strip() for item in args.freq.split(",")]

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL 未配置")
    engine = create_engine(database_url)
    store = SqlAlchemyPitStore(sessionmaker(engine))

    use_ifind = args.source == "ifind" or (
        args.source == "auto" and bool(os.environ.get("IFIND_REFRESH_TOKEN"))
    )

    total = 0
    if "1d" in freqs:
        if use_ifind:
            rows = _ifind_daily(instruments, start, end)
            print(f"[1d] iFinD 拉取 {len(rows)} 行（FORMAL）")
        else:
            rows = _akshare_bars(instruments, start, end, "1d")
            print(f"[1d] AkShare 拉取 {len(rows)} 行（EXPLORATORY）")
        total += store.persist(rows)
    if "5m" in freqs:
        # iFinD 分钟接口（high_frequency）契约未验证，先只走 AkShare
        rows = _akshare_bars(instruments, start, end, "5m")
        print(f"[5m] AkShare 拉取 {len(rows)} 行（EXPLORATORY）")
        total += store.persist(rows)

    print(f"[入库] 新增 {total} 行")
    for entry in store.coverage(instrument_ids=instruments):
        print(
            f"  {entry.instrument_id} {entry.field_prefix} "
            f"{entry.first_event[:10]} → {entry.last_event[:10]} "
            f"({entry.row_count} 行, {entry.artifact_class}, {entry.source_id})"
        )


if __name__ == "__main__":
    main()
