"""端到端验证：期货分钟量价 → 分钟级 PIT 快照 → 分钟因子重算（验收标准 1）。

用数据源门面（AKShare 优先）拉取螺纹钢 5 分钟线，转成 FORMAL 分钟级 PIT
快照（量价数据发布即最终，天然 PIT），再重算 60 分钟动量因子（12 根 5 分钟
bar 的收益），证明分钟级链路成立。

运行：
    docker compose run --rm --no-deps api sh -c \\
        'uv pip install -q akshare && python scripts/verify-futures-minute-pipeline.py'
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from quant_platform.data_gateway.models import FrozenSnapshot
from quant_platform.data_gateway.resolver import BarSeries

SHANGHAI = ZoneInfo("Asia/Shanghai")

MINUTE_MOMENTUM_IR: dict = {
    "schema_version": "factor-ir/v1",
    "factor_id": "classic.cn_futures.minute_momentum_60m",
    "version": "1.0.0",
    "market_scope": {
        "market": "CN_COMMODITY_FUTURES",
        "frequency": "5m",
        "universe_ref": "universe://cn-commodity-liquid-pit/v1",
        "exchange_scope": ["SHFE", "INE", "DCE", "CZCE", "GFEX"],
        "contract_chain_ref": "chain://commodity/main-volume-pit/v1",
        "roll_policy_ref": "policy://roll/volume-no-future/v1",
    },
    "decision_clock": {
        "signal_time": "T_BAR+1m",
        "earliest_trade_time": "T_BAR+2m",
    },
    "inputs": [
        {
            "alias": "close",
            "field_ref": "market.minute.close",
            "data_type": "ScalarSeries",
            "unit": "CNY",
            "available_time_rule": "T_BAR+1m",
        }
    ],
    "expression": {
        "op": "returns",
        "args": [{"ref": "close"}],
        "params": {"periods": 12},
    },
    "validation_policy_ref": "policy://cn-commodity-daily-factor/v1",
}


def main() -> None:
    from quant_platform.data_gateway.resolver import BarRequest, default_provider_chain

    resolver = default_provider_chain()
    request = BarRequest(
        asset_type="futures",
        symbol="RB2610",
        timeframe="5m",
        start=datetime(2026, 8, 14, 9, 0, tzinfo=SHANGHAI),
        end=datetime(2026, 8, 14, 23, 0, tzinfo=SHANGHAI),
    )
    series = resolver.fetch(request)
    print(
        f"[数据源] {series.source_id}，拉取 {len(series.bars)} 根 5 分钟 bar"
        f"（quality_issues={list(series.quality_issues)}）"
    )
    assert series.bars, "分钟 bar 为空"

    # 1. 分钟级 PIT 快照（FORMAL：量价发布即最终）
    snapshot = _pit_snapshot(series)
    print(f"[PIT] 快照 {snapshot.snapshot_id} 含 {len(snapshot.rows)} 行（FORMAL）")

    # 2. 分钟因子重算
    momentum = _execute_momentum(series)
    last = momentum[-5:]
    print(f"[因子] 60 分钟动量，最近 5 个值: {[round(v, 6) for v in last]}")
    assert momentum, "分钟动量因子未产出观测"

    print()
    print("=== 期货分钟链路验证通过：量价 → 分钟 PIT → 分钟因子重算 ===")
    print(f"[校验] 最后动量值 = {round(momentum[-1], 6)}")


def _pit_snapshot(series: BarSeries) -> FrozenSnapshot:
    from quant_platform.data_gateway.models import (
        ArtifactClass,
        DatasetContract,
        FieldContract,
        FrozenSnapshot,
        PITRow,
        QueryPurpose,
        SourceClass,
    )

    ingested = datetime.now(UTC)
    rows: list[PITRow] = []
    for bar in series.bars:
        available = bar.timestamp + timedelta(minutes=1)
        rows.append(
            PITRow(
                dataset_id="market-minute",
                field="market.minute.close",
                instrument_id="RB2610.SHF",
                event_time=bar.timestamp,
                available_time=available,
                ingested_at=ingested,
                revision_id="exchange-official",
                source_id=series.source_id,
                license_tag="formal",
                value=bar.close,
            )
        )
    contract = DatasetContract(
        dataset_id="market-minute",
        source_id=series.source_id,
        source_class=SourceClass.FORMAL,
        fields=(
            FieldContract(
                name="market.minute.close",
                value_type="decimal",
                unit="CNY",
                license_tag="formal",
                allowed_purposes=frozenset({QueryPurpose.RESEARCH}),
            ),
        ),
    )
    return FrozenSnapshot.create(
        snapshot_id=f"snapshot-futures-minute-{ingested.strftime('%Y%m%d')}",
        frozen_at=ingested,
        contracts=(contract,),
        rows=tuple(rows),
        artifact_class=ArtifactClass.FORMAL,
    )


def _execute_momentum(series: BarSeries) -> list[float]:
    from quant_platform.factor_executor.executor import execute_factor
    from quant_platform.factor_executor.model import FactorInputRow, FactorTable
    from quant_platform.factor_ir import compile_factor_ir

    table = FactorTable(
        rows=tuple(
            FactorInputRow(
                timestamp=bar.timestamp,
                instrument_id="RB2610.SHF",
                values={"close": float(bar.close)},
            )
            for bar in series.bars
        )
    )
    compiled = compile_factor_ir(MINUTE_MOMENTUM_IR)
    result = execute_factor(compiled, table)
    return [float(obs.value) for obs in result.observations if obs.value is not None]


if __name__ == "__main__":
    main()
