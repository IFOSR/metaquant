"""端到端验证：真实数据 → PIT 快照 → 因子重算（验收标准 1、3）。

使用 AkShare（第一选择数据源）拉取真实 A 股与商品期货日线，转成
EXPLORATORY PIT 快照，再重算经典动量因子，证明「真实数据能进 PIT 结构并被
Factor IR 编译重算」。

需要网络与 akshare 依赖（容器内：uv pip install akshare）。
运行：
    docker compose run --rm --no-deps api sh -c \\
        'uv pip install -q akshare && python scripts/verify-real-data-pipeline.py'
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")

MOMENTUM_IR: dict = {
    "schema_version": "factor-ir/v1",
    "factor_id": "classic.cn_a.price_momentum_20d",
    "version": "1.0.0",
    "market_scope": {
        "market": "CN_A",
        "frequency": "1d",
        "universe_ref": "universe://cn-a-liquid-pit/v1",
    },
    "decision_clock": {
        "signal_time": "T_CLOSE+30m",
        "earliest_trade_time": "T+1_OPEN",
    },
    "inputs": [
        {
            "alias": "close",
            "field_ref": "market.eod.close_adjusted",
            "data_type": "ScalarSeries",
            "unit": "CNY",
            "available_time_rule": "T_CLOSE+20m",
        }
    ],
    "expression": {
        "op": "returns",
        "args": [{"ref": "close"}],
        "params": {"periods": 20},
    },
    "validation_policy_ref": "policy://cn-a-daily-factor/v1",
}


def _load_akshare() -> object:
    import akshare as ak

    return ak


def _parse_date(value: object) -> datetime:
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()  # type: ignore[union-attr]
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _pit_rows(
    records: list[tuple[datetime, float]],
    *,
    instrument_id: str,
    field: str,
    ingested: datetime,
    revision: str,
) -> list[object]:
    from quant_platform.data_gateway.models import PITRow

    rows: list[object] = []
    for trade_time, value in records:
        event_time = trade_time.replace(hour=15, minute=0, tzinfo=SHANGHAI)
        rows.append(
            PITRow(
                dataset_id="market-eod",
                field=field,
                instrument_id=instrument_id,
                event_time=event_time,
                available_time=event_time.replace(minute=30),
                ingested_at=ingested,
                revision_id=revision,
                source_id="akshare-cn",
                license_tag="exploratory",
                value=value,
            )
        )
    return rows


def _snapshot(rows: list[object], field: str, ingested: datetime) -> object:
    from quant_platform.data_gateway.models import (
        ArtifactClass,
        DatasetContract,
        FieldContract,
        FrozenSnapshot,
        QueryPurpose,
        SourceClass,
    )

    contract = DatasetContract(
        dataset_id="market-eod",
        source_id="akshare-cn",
        source_class=SourceClass.EXPLORATORY,
        fields=(
            FieldContract(
                name=field,
                value_type="decimal",
                unit="CNY",
                license_tag="exploratory",
                allowed_purposes=frozenset({QueryPurpose.RESEARCH}),
            ),
        ),
    )
    return FrozenSnapshot.create(
        snapshot_id=f"snapshot-akshare-{ingested.strftime('%Y%m%d')}",
        frozen_at=ingested,
        contracts=(contract,),
        rows=tuple(rows),
        artifact_class=ArtifactClass.EXPLORATORY,
    )


def _execute_momentum(records: list[tuple[datetime, float]]) -> list[float]:
    from quant_platform.factor_executor.executor import execute_factor
    from quant_platform.factor_executor.model import FactorInputRow, FactorTable
    from quant_platform.factor_ir import compile_factor_ir

    table = FactorTable(
        rows=tuple(
            FactorInputRow(
                timestamp=trade_time.replace(hour=15, minute=0, tzinfo=SHANGHAI),
                instrument_id="600000.SH",
                values={"close": value},
            )
            for trade_time, value in records
        )
    )
    compiled = compile_factor_ir(MOMENTUM_IR)
    result = execute_factor(compiled, table)
    return [float(obs.value) for obs in result.observations if obs.value is not None]


def main() -> None:
    ak = _load_akshare()
    ingested = datetime.now(UTC)

    # 1. A 股：浦发银行前复权日线（足够 20 日动量）
    frame = ak.stock_zh_a_hist(  # type: ignore[attr-defined]
        symbol="600000",
        period="daily",
        start_date="20260501",
        end_date="20260815",
        adjust="qfq",
    )
    records = [
        (_parse_date(row["日期"]), float(row["收盘"])) for _, row in frame.iterrows()
    ]
    records.sort(key=lambda item: item[0])
    print(f"[A股] 600000.SH 拉取 {len(records)} 条日线")

    # 2. PIT 快照
    rows = _pit_rows(
        records,
        instrument_id="600000.SH",
        field="market.eod.close_adjusted",
        ingested=ingested,
        revision="akshare-20260815",
    )
    snapshot = _snapshot(rows, "market.eod.close_adjusted", ingested)
    print(f"[PIT] 快照 {snapshot.snapshot_id} 含 {len(snapshot.rows)} 行")

    # 3. 因子重算
    momentum = _execute_momentum(records)
    print(f"[因子] 20 日动量，最近 5 个值: {[round(v, 6) for v in momentum[-5:]]}")
    assert momentum, "动量因子未产出任何观测"

    # 4. 期货：螺纹钢结算价（验证期货字段）
    futures = ak.futures_zh_daily_sina(symbol="RB2610")  # type: ignore[attr-defined]
    print(f"[期货] RB2610 拉取 {len(futures)} 条日线")
    print(
        "[期货] 最近 3 日结算价:",
        [float(v) for v in futures["settle"].tail(3).tolist()],
    )

    print()
    print("=== 端到端验证通过：真实数据 → PIT 快照 → 因子重算 ===")
    print(f"[校验] 动量因子最后值 = {round(momentum[-1], 6)}")


if __name__ == "__main__":
    main()
