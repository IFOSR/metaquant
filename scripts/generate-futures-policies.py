"""生成期货验证策略 + 标签快照（G18 数据接入）。

从 formal-snapshots.json 的期货日频 close 数据计算 5 天前向收益，生成：
1. 期货验证策略（追加到 config/validation-policies.json）
2. 期货标签快照（追加到 config/label-snapshots.json）
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path

SNAPSHOT_PATH = Path("config/formal-snapshots.json")
POLICY_PATH = Path("config/validation-policies.json")
LABEL_PATH = Path("config/label-snapshots.json")


def load_snapshot() -> dict[str, object]:
    doc = json.loads(SNAPSHOT_PATH.read_text())
    for item in doc:
        if item.get("snapshot_id") == "snapshot-cn-futures-eod-001":
            return item
    raise RuntimeError("期货日频快照不存在")


def close_series(snapshot: dict[str, object]) -> dict[str, dict[date, float]]:
    series: dict[str, dict[date, float]] = {}
    for row in snapshot["rows"]:
        if row.get("field") != "market.eod.close":
            continue
        instrument = str(row["instrument_id"])
        day = datetime.fromisoformat(
            str(row["event_time"]).replace("Z", "+00:00")
        ).date()
        series.setdefault(instrument, {})[day] = float(row["value"])
    return series


def forward_returns(
    series: dict[str, dict[date, float]], horizon: int
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for instrument, closes in series.items():
        days = sorted(closes)
        for index, day in enumerate(days):
            future = index + horizon
            if future >= len(days):
                continue
            forward = closes[days[future]] / closes[day] - 1.0
            # event_time 必须与行情快照行保持一致（T 日 15:00 UTC 收盘），
            # 否则校验器按 (instrument, event_time) 精确对齐时匹配不到任何横截面。
            event_time = datetime.combine(day, time(15, 0)).isoformat() + "+00:00"
            available_day = days[future]
            available_time = (
                datetime.combine(available_day, time(15, 0)).isoformat() + "+00:00"
            )
            rows.append(
                {
                    "instrument_id": instrument,
                    "event_time": event_time,
                    "available_time": available_time,
                    "value": round(forward, 8),
                }
            )
    return rows


def main() -> None:
    snapshot = load_snapshot()
    series = close_series(snapshot)
    horizon = 5

    # 1. 期货验证策略
    policy = {
        "schema_version": "validation-policy/v1",
        "policy_id": "policy://cn-futures-daily-factor/v1",
        "market": "CN_COMMODITY_FUTURES",
        "min_coverage": 0.1,
        "min_observations": 2,
        "max_constant_ratio": 1.0,
        "ic_sign": "ANY",
        "min_icir": 0.0,
        "min_nw_t": 0.0,
        "quantile_count": 5,
        "decay_horizons": [1, 5],
    }
    policies = json.loads(POLICY_PATH.read_text())
    policies = [p for p in policies if p["market"] != "CN_COMMODITY_FUTURES"]
    policies.append(policy)
    POLICY_PATH.write_text(json.dumps(policies, ensure_ascii=False, indent=2) + "\n")

    # 2. 期货标签快照
    label = {
        "schema_version": "label-snapshot/v1",
        "snapshot_id": "label-snapshot-cn-futures-001",
        "sealed": True,
        "artifact_class": "FORMAL_LABEL",
        "label": {
            "label_id": "label://cn-futures-fwd-5d/v1",
            "market": "CN_COMMODITY_FUTURES",
            "horizon": horizon,
            "field_ref": "market.eod.forward_return_5d",
            "return_definition": "close_to_close",
        },
        "rows": forward_returns(series, horizon),
    }
    labels = json.loads(LABEL_PATH.read_text())
    labels = [
        item for item in labels if item["label"]["market"] != "CN_COMMODITY_FUTURES"
    ]
    labels.append(label)
    LABEL_PATH.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n")

    print(f"[策略] 期货验证策略 {policy['policy_id']}")
    print(f"[标签] 期货标签快照 {len(label['rows'])} 行（horizon={horizon}）")
    print(f"[合约] {sorted(series)}")


if __name__ == "__main__":
    main()
