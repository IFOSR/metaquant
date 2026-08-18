"""从 pit_observations 表重新生成 formal + label 快照（替换 15 天 demo 数据）。

用数据库中的真实 iFinD 日频数据（约 180-205 个交易日）重建正式快照，
并根据收盘价计算未来 5 日收益标签，让验证环节能跑出真实的 IC。

运行（在 api 容器内，需 DATABASE_URL 与可写 config 目录）：
    python scripts/regenerate-snapshots.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

FORMAL_PATH = Path("config/formal-snapshots.json")
LABEL_PATH = Path("config/label-snapshots.json")

EOD_FIELDS = (
    "market.eod.open",
    "market.eod.high",
    "market.eod.low",
    "market.eod.close",
    "market.eod.volume",
    "market.eod.open_interest",
    "market.eod.settlement",
)

UNITS = {
    "market.eod.open": "CNY",
    "market.eod.high": "CNY",
    "market.eod.low": "CNY",
    "market.eod.close": "CNY",
    "market.eod.volume": "lot",
    "market.eod.open_interest": "lot",
    "market.eod.settlement": "CNY",
}


def _load_formal_rows() -> list[dict[str, object]]:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT instrument_id, field, event_time, available_time, "
                "ingested_at, revision_id, value "
                "FROM pit_observations "
                "WHERE source_id = 'ifind-cn' AND field LIKE 'market.eod.%' "
                "ORDER BY instrument_id, event_time, field"
            )
        )
        return [dict(row._mapping) for row in result]


def _iso(value: object) -> str:
    return value.astimezone(timezone.utc).isoformat()  # type: ignore[union-attr]


def _snapshot_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "dataset_id": "market-eod",
            "field": row["field"],
            "instrument_id": row["instrument_id"],
            "event_time": _iso(row["event_time"]),
            "available_time": _iso(row["available_time"]),
            "ingested_at": _iso(row["ingested_at"]),
            "revision_id": row["revision_id"],
            "source_id": "ifind-cn",
            "license_tag": "licensed-research",
            "value": float(row["value"]),  # type: ignore[arg-type]
        }
        for row in rows
    ]


def _label_rows(
    rows: list[dict[str, object]], horizon: int = 5
) -> tuple[list[dict[str, object]], object]:
    closes: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        if row["field"] == "market.eod.close":
            closes.setdefault(str(row["instrument_id"]), []).append(row)

    # 全市场交易日序列；决策时点取数据末尾前 2*horizon 个交易日，
    # 保证既有足够历史算因子，又给未来收益留出 horizon 天的空间。
    all_times = sorted({r["event_time"] for r in rows})
    if len(all_times) <= 2 * horizon:
        decision_time = all_times[horizon] if len(all_times) > horizon else all_times[-1]
    else:
        decision_time = all_times[-(2 * horizon)]
    decision_index = all_times.index(decision_time)
    valid = set(all_times[decision_index - horizon + 1 : decision_index + 1])

    label_rows: list[dict[str, object]] = []
    for series in closes.values():
        series.sort(key=lambda r: r["event_time"])  # type: ignore[arg-type, return-value]
        for i in range(len(series) - horizon):
            t0 = series[i]
            if t0["event_time"] not in valid:
                continue
            t5 = series[i + horizon]
            c0 = float(t0["value"])  # type: ignore[arg-type]
            c5 = float(t5["value"])  # type: ignore[arg-type]
            if c0 <= 0:
                continue
            label_rows.append(
                {
                    "instrument_id": t0["instrument_id"],
                    "event_time": _iso(t0["event_time"]),
                    "available_time": _iso(t5["available_time"]),
                    "value": (c5 - c0) / c0,
                }
            )
    return label_rows, decision_time


def build_formal_snapshot(rows: list[dict[str, object]]) -> dict[str, object]:
    last = max(r["ingested_at"] for r in rows)  # type: ignore[arg-type, return-value]
    fields = [
        {
            "name": name,
            "value_type": "decimal",
            "unit": UNITS[name],
            "license_tag": "licensed-research",
            "allowed_purposes": ["RESEARCH"],
        }
        for name in EOD_FIELDS
    ]
    return {
        "snapshot_id": "snapshot-cn-futures-eod-001",
        "frozen_at": _iso(last),
        "sealed": True,
        "artifact_class": "FORMAL",
        "market": "CN_COMMODITY_FUTURES",
        "universe_ref": "futures:liquid-initial",
        "frequency": "1d",
        "decision_clock": "T_CLOSE+30m",
        "trade_clock": "T+1_OPEN",
        "settlement_clock": "T+1_SETTLEMENT",
        "exchange_scope": ["SHFE"],
        "contract_chain_ref": "chain://shfe-rb/v1",
        "roll_policy_ref": "roll-policy://oi-confirmed-3d/v1",
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
        "rows": _snapshot_rows(rows),
    }


def build_label_snapshot(
    rows: list[dict[str, object]],
) -> tuple[dict[str, object], object]:
    label_rows, decision_time = _label_rows(rows)
    return (
        {
            "schema_version": "label-snapshot/v1",
            "snapshot_id": "label-snapshot-cn-futures-001",
            "sealed": True,
            "artifact_class": "FORMAL_LABEL",
            "label": {
                "label_id": "label://cn-futures-fwd-5d/v1",
                "market": "CN_COMMODITY_FUTURES",
                "horizon": 5,
                "field_ref": "market.eod.forward_return_5d",
                "return_definition": "close_to_close",
            },
            "rows": label_rows,
        },
        decision_time,
    )


def main() -> None:
    rows = _load_formal_rows()
    print(f"[db] 读入 formal 日频 {len(rows)} 行")
    if not rows:
        raise SystemExit("数据库中没有 formal 日频数据，请先运行 ingest-market-data.py")

    formal = build_formal_snapshot(rows)
    label, decision_time = build_label_snapshot(rows)

    existing_formal = json.loads(FORMAL_PATH.read_text())
    kept = [
        s for s in existing_formal if s.get("snapshot_id") != "snapshot-cn-futures-eod-001"
    ]
    kept.append(formal)
    FORMAL_PATH.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n")

    existing_label = json.loads(LABEL_PATH.read_text())
    kept_label = [
        s for s in existing_label if s.get("snapshot_id") != "label-snapshot-cn-futures-001"
    ]
    kept_label.append(label)
    LABEL_PATH.write_text(json.dumps(kept_label, ensure_ascii=False, indent=2) + "\n")

    formal_rows = formal["rows"]
    label_rows = label["rows"]
    assert isinstance(formal_rows, list) and isinstance(label_rows, list)
    print(f"[formal] 快照 rows={len(formal_rows)}")
    print(f"[label] 标签 rows={len(label_rows)}，decision_time={_iso(decision_time)}")
    print("已写入 config/formal-snapshots.json 和 config/label-snapshots.json")


if __name__ == "__main__":
    main()
