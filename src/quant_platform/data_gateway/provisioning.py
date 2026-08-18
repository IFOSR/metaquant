"""按需数据供给：把采集 + 密封收编为服务。

这是"研究任务驱动的数据管线"的第二环。之前采集（ingest）和密封
（regenerate）是独立手工脚本，现在收编为 :class:`DataProvisioning`：
给定一个解析好的标的池，采集数据入库，生成密封的 formal + label 快照，
返回预注册所需的 snapshot_id / manifest_hash / decision_time。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4

from quant_platform.data_gateway.ifind_client import (
    IFindClient,
    fetch_futures_daily,
    futures_daily_to_pit_rows,
)
from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.data_gateway.universe import UniverseSpec
from quant_platform.experiments import canonical_hash

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


@dataclass(frozen=True, slots=True)
class ProvisionResult:
    snapshot_id: str
    snapshot_manifest_hash: str
    decision_time: str
    instrument_count: int
    row_count: int
    formal_snapshot: dict[str, object]
    label_snapshot: dict[str, object]
    label_manifest_hash: str


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def build_formal_snapshot(
    rows: tuple[RawPITRow, ...] | list[RawPITRow],
    *,
    snapshot_id: str,
    universe_ref: str,
) -> dict[str, object]:
    last = max(row.ingested_at for row in rows)
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
    snapshot_rows = [
        {
            "dataset_id": "market-eod",
            "field": row.field,
            "instrument_id": row.instrument_id,
            "event_time": _iso(row.event_time),
            "available_time": _iso(row.available_time),
            "ingested_at": _iso(row.ingested_at),
            "revision_id": row.revision_id,
            "source_id": row.source_id,
            "license_tag": "licensed-research",
            "value": float(row.value),
        }
        for row in rows
        if row.field in EOD_FIELDS
    ]
    return {
        "snapshot_id": snapshot_id,
        "frozen_at": _iso(last),
        "sealed": True,
        "artifact_class": "FORMAL",
        "market": "CN_COMMODITY_FUTURES",
        "universe_ref": universe_ref,
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
        "rows": snapshot_rows,
    }


def build_label_snapshot(
    rows: tuple[RawPITRow, ...] | list[RawPITRow],
    *,
    snapshot_id: str,
    horizon: int = 5,
) -> tuple[dict[str, object], str]:
    closes: dict[str, list[RawPITRow]] = {}
    for row in rows:
        if row.field == "market.eod.close":
            closes.setdefault(row.instrument_id, []).append(row)

    # 全市场交易日序列；决策时点取数据末尾前 2*horizon 个交易日，
    # 保证既有足够历史算因子，又给未来收益留出 horizon 天的空间。
    all_times = sorted({row.event_time for row in rows})
    if len(all_times) <= 2 * horizon:
        decision_time = (
            all_times[horizon] if len(all_times) > horizon else all_times[-1]
        )
    else:
        decision_time = all_times[-(2 * horizon)]
    decision_index = all_times.index(decision_time)
    valid = set(all_times[decision_index - horizon + 1 : decision_index + 1])

    label_rows: list[dict[str, object]] = []
    for series in closes.values():
        series.sort(key=lambda r: r.event_time)
        for i in range(len(series) - horizon):
            t0 = series[i]
            if t0.event_time not in valid:
                continue
            t5 = series[i + horizon]
            c0 = float(t0.value)
            c5 = float(t5.value)
            if c0 <= 0:
                continue
            label_rows.append(
                {
                    "instrument_id": t0.instrument_id,
                    "event_time": _iso(t0.event_time),
                    "available_time": _iso(t5.available_time),
                    "value": (c5 - c0) / c0,
                }
            )

    label_snapshot = {
        "schema_version": "label-snapshot/v1",
        "snapshot_id": snapshot_id,
        "sealed": True,
        "artifact_class": "FORMAL_LABEL",
        "label": {
            "label_id": "label://cn-futures-fwd-5d/v1",
            "market": "CN_COMMODITY_FUTURES",
            "horizon": horizon,
            "field_ref": "market.eod.forward_return_5d",
            "return_definition": "close_to_close",
        },
        "rows": label_rows,
    }
    return label_snapshot, _iso(decision_time)


class DataProvisioning:
    def __init__(self, store: SqlAlchemyPitStore) -> None:
        self.store = store

    def provision(
        self,
        spec: UniverseSpec,
        *,
        start: date,
        end: date,
        snapshot_id: str | None = None,
    ) -> ProvisionResult:
        rows = self._collect(spec.instruments, start, end)
        if not rows:
            raise ValueError("no data collected for the requested universe")
        self.store.persist(rows)

        sid = snapshot_id or f"snapshot-cn-futures-{uuid4().hex[:12]}"
        formal = build_formal_snapshot(
            rows, snapshot_id=sid, universe_ref=spec.universe_ref
        )
        label, decision_time = build_label_snapshot(rows, snapshot_id=f"label-{sid}")

        return ProvisionResult(
            snapshot_id=sid,
            snapshot_manifest_hash=canonical_hash(formal),
            decision_time=decision_time,
            instrument_count=len({row.instrument_id for row in rows}),
            row_count=len(rows),
            formal_snapshot=formal,
            label_snapshot=label,
            label_manifest_hash=canonical_hash(label),
        )

    def _collect(
        self, instruments: tuple[str, ...], start: date, end: date
    ) -> tuple[RawPITRow, ...]:
        refresh_token = os.environ.get("IFIND_REFRESH_TOKEN", "").strip()
        if not refresh_token:
            raise ValueError("IFIND_REFRESH_TOKEN is not configured")
        client = IFindClient(refresh_token=refresh_token)
        market_data = fetch_futures_daily(
            client,
            tuple(instruments),
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
        )
        return futures_daily_to_pit_rows(
            market_data, source_id="ifind-cn", ingested_at=datetime.now(UTC)
        )
