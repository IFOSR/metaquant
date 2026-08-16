"""生成 formal-snapshots.json：真实期货量价 + 分钟级快照（G18 数据接入）。

用 iFinD 拉期货日频量价（OHLC + 成交量 + 持仓量 + 结算价）、AkShare 拉期货
分钟线，转成 formal-snapshots.json 格式，让研究任务能用真实期货数据跑因子。

运行：
    docker compose run --rm --no-deps api python scripts/generate-formal-snapshots.py
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from quant_platform.data_gateway.ifind_client import (
    IFindClient,
    fetch_futures_daily,
)

CONFIG_PATH = Path("config/formal-snapshots.json")

FUTURE_CODES = ("RB2610.SHF", "AU2612.SHF")


def _field(name: str, unit: str = "1") -> dict[str, object]:
    return {
        "name": name,
        "value_type": "decimal",
        "unit": unit,
        "license_tag": "licensed-research",
        "allowed_purposes": ["RESEARCH"],
    }


def _rows(
    market_data: dict[str, dict[str, dict[str, object]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for code, dates in market_data.items():
        for date_str, fields in sorted(dates.items()):
            event_time = f"{date_str}T15:00:00+00:00"
            for name, value in fields.items():
                if not isinstance(value, int | float) or float(value) < 0:
                    continue
                rows.append(
                    {
                        "dataset_id": "market-eod",
                        "field": f"market.eod.{name}",
                        "instrument_id": code,
                        "event_time": event_time,
                        "available_time": event_time,
                        "ingested_at": event_time,
                        "revision_id": "ifind-live",
                        "source_id": "ifind-cn",
                        "license_tag": "licensed-research",
                        "value": value,
                    }
                )
    return rows


def build_futures_daily_snapshot(
    client: IFindClient,
    *,
    snapshot_id: str,
    start: str,
    end: str,
) -> dict[str, object]:
    market_data = fetch_futures_daily(client, FUTURE_CODES, start, end)
    fields = [
        _field("market.eod.open", "CNY"),
        _field("market.eod.high", "CNY"),
        _field("market.eod.low", "CNY"),
        _field("market.eod.close", "CNY"),
        _field("market.eod.volume", "lot"),
        _field("market.eod.open_interest", "lot"),
        _field("market.eod.settlement", "CNY"),
    ]
    return {
        "snapshot_id": snapshot_id,
        "frozen_at": f"{end}T15:00:00+00:00",
        "sealed": True,
        "artifact_class": "FORMAL",
        "market": "CN_COMMODITY_FUTURES",
        "universe_ref": "futures:liquid-initial",
        "frequency": "1d",
        "decision_clock": "T_CLOSE+30m",
        "trade_clock": "T+1_OPEN",
        "purpose": "RESEARCH",
        "allowed_license_tags": ["licensed-research"],
        "datasets": [
            {
                "dataset_id": "market-eod",
                "source_id": "ifind-cn",
                "source_class": "FORMAL",
                "fields": fields,
            }
        ],
        "rows": _rows(market_data),
    }


def build_futures_minute_snapshot(
    *,
    snapshot_id: str,
    symbol: str,
    period: str = "5",
) -> dict[str, object]:
    """用 AkShare 拉期货分钟线，生成分钟级快照。"""
    import akshare as ak  # type: ignore[import-not-found]

    frame = ak.futures_zh_minute_sina(symbol=symbol, period=period)
    rows: list[dict[str, object]] = []
    for _, record in frame.iterrows():
        timestamp = record["datetime"]
        ts_str = str(timestamp).replace(" ", "T") + "+00:00"
        for name in ("open", "high", "low", "close", "volume", "hold"):
            value = record.get(name)
            if value is None:
                continue
            rows.append(
                {
                    "dataset_id": "market-minute",
                    "field": f"market.minute.{name}",
                    "instrument_id": f"{symbol}.SHF",
                    "event_time": ts_str,
                    "available_time": ts_str,
                    "ingested_at": ts_str,
                    "revision_id": "akshare-live",
                    "source_id": "akshare-cn",
                    "license_tag": "licensed-research",
                    "value": float(value),
                }
            )
    fields = [
        _field("market.minute.open", "CNY"),
        _field("market.minute.high", "CNY"),
        _field("market.minute.low", "CNY"),
        _field("market.minute.close", "CNY"),
        _field("market.minute.volume", "lot"),
        _field("market.minute.hold", "lot"),
    ]
    return {
        "snapshot_id": snapshot_id,
        "frozen_at": datetime.now(UTC).isoformat(),
        "sealed": True,
        "artifact_class": "FORMAL",
        "market": "CN_COMMODITY_FUTURES",
        "universe_ref": "futures:liquid-initial",
        "frequency": f"{period}m",
        "decision_clock": "T_BAR+1m",
        "trade_clock": "T_BAR+1m",
        "purpose": "RESEARCH",
        "allowed_license_tags": ["licensed-research"],
        "datasets": [
            {
                "dataset_id": "market-minute",
                "source_id": "akshare-cn",
                "source_class": "FORMAL",
                "fields": fields,
            }
        ],
        "rows": rows,
    }


def main() -> None:
    client = IFindClient()
    end = date(2026, 8, 15)
    start = end.replace(day=1)
    snapshot = build_futures_daily_snapshot(
        client,
        snapshot_id="snapshot-cn-futures-eod-001",
        start=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    minute = build_futures_minute_snapshot(
        snapshot_id="snapshot-cn-futures-5m-001",
        symbol="RB2610",
    )
    daily_rows = snapshot["rows"]
    minute_rows = minute["rows"]
    assert isinstance(daily_rows, list)
    assert isinstance(minute_rows, list)
    # 保留现有 A 股快照 + 追加期货快照
    existing: list[dict[str, object]] = []
    if CONFIG_PATH.exists():
        existing = json.loads(CONFIG_PATH.read_text())
    combined = [
        item for item in existing if item.get("market") != "CN_COMMODITY_FUTURES"
    ]
    combined.extend((snapshot, minute))
    CONFIG_PATH.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n")
    print(
        f"[快照] 已写入 {CONFIG_PATH}：期货日频 {len(daily_rows)} 行"
        f" + 分钟 {len(minute_rows)} 行"
    )
    print(f"[快照] 合约: {FUTURE_CODES}")


if __name__ == "__main__":
    main()
