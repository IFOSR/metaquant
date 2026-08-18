"""POST /v1/backtests 端到端测试（期货日频，sqlite + 内存 artifact store）。

链路：预注册期货因子实验 → 运行 → 校验 → 晋级（进 Alpha 池）→
GET /v1/alpha-pool 富化字段 → POST /v1/backtests 跑 Nautilus 回测。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.api.app import create_app
from quant_platform.artifacts import InMemoryArtifactStore
from quant_platform.experiment_runtime import (
    ExecutionIdentity,
    InMemoryFormalSnapshotCatalog,
)
from quant_platform.experiment_runtime.repository import (
    SqlAlchemyExperimentRepository,
)
from quant_platform.experiments import canonical_hash
from quant_platform.research.models import Base
from quant_platform.research.repository import SqlAlchemyResearchRepository
from quant_platform.validation import (
    FormalLabelSnapshot,
    ForwardReturnLabel,
    ICSign,
    InMemoryLabelSnapshotCatalog,
    InMemoryPromotionPolicyCatalog,
    InMemoryValidationPolicyCatalog,
    LabelSnapshotRow,
    PromotionPolicy,
    ValidationPolicy,
)
from tests.experiment_support import headers, metadata

START = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
INSTRUMENTS = ("RB2610.SHF", "AU2612.SHF")

EXECUTION_IDENTITY = ExecutionIdentity(
    code_sha="a" * 40,
    image_digest="sha256:" + "b" * 64,
    dependency_lock_hash="c" * 64,
    executor_version="factor-executor/v1",
    config_hash="d" * 64,
)


def futures_snapshot() -> dict[str, object]:
    fields = [
        {
            "name": f"market.eod.{name}",
            "value_type": "decimal",
            "unit": "CNY" if name != "volume" else "lot",
            "license_tag": "licensed-research",
            "allowed_purposes": ["RESEARCH"],
        }
        for name in ("close", "volume")
    ]
    rows: list[dict[str, object]] = []
    for day in range(10):
        ts = (START + timedelta(days=day)).isoformat()
        for index, instrument in enumerate(INSTRUMENTS):
            close = 3000.0 + index * 1000.0 + day * 10.0
            rows.append(
                {
                    "dataset_id": "market-eod",
                    "field": "market.eod.close",
                    "instrument_id": instrument,
                    "event_time": ts,
                    "available_time": ts,
                    "ingested_at": ts,
                    "revision_id": "r1",
                    "source_id": "licensed-source",
                    "license_tag": "licensed-research",
                    "value": close,
                }
            )
            rows.append(
                {
                    "dataset_id": "market-eod",
                    "field": "market.eod.volume",
                    "instrument_id": instrument,
                    "event_time": ts,
                    "available_time": ts,
                    "ingested_at": ts,
                    "revision_id": "r1",
                    "source_id": "licensed-source",
                    "license_tag": "licensed-research",
                    "value": 1000.0,
                }
            )
    return {
        "snapshot_id": "snapshot-futures-test",
        "frozen_at": (START + timedelta(days=11)).isoformat(),
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
                "source_id": "licensed-source",
                "source_class": "FORMAL",
                "fields": fields,
            }
        ],
        "rows": rows,
    }


def futures_factor_ir() -> dict[str, object]:
    return {
        "schema_version": "factor-ir/v1",
        "factor_id": "classic.cn_futures.momentum_1d",
        "version": "1.0.0",
        "market_scope": {
            "market": "CN_COMMODITY_FUTURES",
            "frequency": "1d",
            "universe_ref": "futures:liquid-initial",
            "exchange_scope": ["SHFE"],
            "contract_chain_ref": "chain://shfe-rb/v1",
            "roll_policy_ref": "roll-policy://oi-confirmed-3d/v1",
        },
        "decision_clock": {
            "signal_time": "T_CLOSE+30m",
            "earliest_trade_time": "T+1_OPEN",
        },
        "inputs": [
            {
                "alias": "close",
                "field_ref": "market.eod.close",
                "data_type": "ScalarSeries",
                "unit": "CNY",
                "available_time_rule": "T_CLOSE+20m",
            }
        ],
        "expression": {
            "op": "returns",
            "args": [{"ref": "close"}],
            "params": {"periods": 1},
        },
        "validation_policy_ref": "policy://futures-daily-factor/v1",
    }


def futures_label() -> FormalLabelSnapshot:
    rows = tuple(
        LabelSnapshotRow(
            instrument_id=instrument,
            event_time=START + timedelta(days=day),
            available_time=START + timedelta(days=day + 5),
            value=0.01,
        )
        for instrument in INSTRUMENTS
        for day in range(5)
    )
    return FormalLabelSnapshot(
        snapshot_id="label-futures-test",
        label=ForwardReturnLabel(
            label_id="label://futures-fwd-5d/v1",
            market="CN_COMMODITY_FUTURES",
            horizon=5,
            field_ref="market.eod.forward_return_5d",
        ),
        rows=rows,
    )


def make_client() -> tuple[TestClient, Engine]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    research = SqlAlchemyResearchRepository(engine)
    experiments = SqlAlchemyExperimentRepository(
        engine,
        research_repository=research,
        artifact_store=InMemoryArtifactStore(),
        snapshot_catalog=InMemoryFormalSnapshotCatalog((futures_snapshot(),)),
        execution_identity=EXECUTION_IDENTITY,
        policy_catalog=InMemoryValidationPolicyCatalog(
            (
                ValidationPolicy(
                    policy_id="policy://futures-daily-factor/v1",
                    market="CN_COMMODITY_FUTURES",
                    min_coverage=0.0,
                    min_observations=1,
                    max_constant_ratio=1.0,
                    ic_sign=ICSign.ANY,
                    min_icir=0.0,
                    min_nw_t=0.0,
                    quantile_count=2,
                    decay_horizons=(5,),
                ),
            )
        ),
        label_snapshot_catalog=InMemoryLabelSnapshotCatalog((futures_label(),)),
        promotion_policy_catalog=InMemoryPromotionPolicyCatalog(
            (
                PromotionPolicy(
                    policy_id="policy://futures-promotion/v1",
                    market="CN_COMMODITY_FUTURES",
                    min_coverage=0.0,
                    min_observations=1,
                    min_oos_ic=0.0,
                    fdr_bound=1.0,
                    min_capacity=0.0,
                ),
            )
        ),
    )
    from tests.experiment_support import provider

    client = TestClient(
        create_app(
            readiness_probe=lambda: {"postgres": True, "minio": True},
            research_repository=research,
            experiment_repository=experiments,
            research_principal_provider=provider,
        )
    )
    return client, engine


def _promoted_factor_hash(client: TestClient) -> str:
    job = client.post(
        "/v1/research-jobs",
        headers=headers("bt-create-job-0001"),
        json={
            "metadata": metadata("Create futures research job"),
            "market": "CN_COMMODITY_FUTURES",
            "universe_ref": "futures:liquid-initial",
            "frequency": "1d",
            "decision_clock": "T_CLOSE+30m",
            "trade_clock": "T+1_OPEN",
            "settlement_clock": "T+1_SETTLEMENT",
            "exchange_scope": ["SHFE"],
            "contract_selection": "ACTUAL_CONTRACTS_ONLY",
            "roll_policy": "roll-policy://oi-confirmed-3d/v1",
            "horizon": "5TD",
            "research_brief_version_id": "brief://seed",
        },
    )
    assert job.status_code == 202, job.text
    job_id = job.json()["resource_id"]
    brief = client.post(
        f"/v1/research-jobs/{job_id}/brief-versions",
        headers=headers("bt-create-brief-0001", '"1"'),
        json={
            "metadata": metadata("Create futures brief"),
            "brief": {
                "hypothesis": "Futures momentum persists.",
                "economic_mechanism": "Information diffuses slowly.",
                "expected_direction": "POSITIVE",
                "falsification_conditions": ["coverage drop"],
                "allowed_data_domains": ["formal.market.eod"],
                "forbidden_data_domains": ["future.revisions"],
                "constraints": ["daily only"],
                "evidence_ref_ids": ["evidence://futures-momentum/1"],
                "uncertainties": ["roll timing"],
            },
        },
    )
    brief_id = brief.json()["resource_id"]
    frozen = client.post(
        f"/v1/research-brief-versions/{brief_id}:freeze",
        headers=headers("bt-freeze-brief-0001", '"1"'),
        json=metadata("Freeze brief"),
    )
    assert frozen.status_code == 202

    snapshot = futures_snapshot()
    registered = client.post(
        "/v1/experiments:preregister",
        headers=headers("bt-preregister-0001"),
        json={
            "metadata": metadata("Preregister futures factor"),
            "research_job_id": job_id,
            "brief_version_id": brief_id,
            "decision_time": (START + timedelta(days=4, hours=1)).isoformat(),
            "random_seed": 41,
            "resource_budget": {
                "cpu_seconds": 300,
                "wall_clock_seconds": 600,
                "memory_mb": 2048,
                "max_observations": 10000,
            },
            "factor_ir": futures_factor_ir(),
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_manifest_hash": canonical_hash(snapshot),
        },
    )
    assert registered.status_code == 202, registered.text
    experiment_id = registered.json()["resource_id"]

    run = client.post(
        f"/v1/experiments/{experiment_id}:run",
        headers=headers("bt-run-factor-00001", '"1"'),
        json={"metadata": metadata("Run futures factor")},
    )
    assert run.status_code == 202, run.text
    run_id = run.json()["resource_id"]

    label = futures_label()
    validated = client.post(
        f"/v1/experiment-runs/{run_id}:validate",
        headers=headers("bt-validate-0001"),
        json={
            "metadata": metadata("Validate futures factor"),
            "policy_id": "policy://futures-daily-factor/v1",
            "label_snapshot_id": label.snapshot_id,
            "label_snapshot_manifest_hash": label.content_hash(),
        },
    )
    assert validated.status_code == 202, validated.text

    report = client.get(
        f"/v1/experiment-runs/{run_id}/validation", headers=headers()
    ).json()
    quality = report["data_quality"]
    promoted = client.post(
        f"/v1/experiment-runs/{run_id}:promote",
        headers=headers("bt-promote-000001"),
        json={
            "metadata": metadata("Promote futures factor"),
            "policy_id": "policy://futures-promotion/v1",
            "direction": "LONG_SHORT",
            "universe": "futures-liquid",
            "horizon": 5,
            "risk_premium": False,
            "evidence": {
                "coverage": quality["coverage_ratio"],
                "observations": quality["observation_count"],
                "oos_ic": 0.05,
                "expected_direction": "POSITIVE",
                "fdr_qvalue": 0.03,
                "capacity_aum": 1_000_000.0,
                "sharpe": 1.0,
                "effect_score": 0.8,
                "stability_score": 0.7,
                "independence_score": 0.9,
                "cost_value_score": 0.6,
                "interpretability_score": 0.5,
            },
        },
    )
    assert promoted.status_code == 202, promoted.text
    pool = client.get("/v1/alpha-pool", headers=headers()).json()["items"]
    assert len(pool) == 1
    return str(pool[0]["factor_ir_hash"])


def test_alpha_pool_items_include_factor_id_and_instruments() -> None:
    client, _ = make_client()
    with client:
        _promoted_factor_hash(client)
        item = client.get("/v1/alpha-pool", headers=headers()).json()["items"][0]
        assert item["factor_id"] == "classic.cn_futures.momentum_1d"
        assert sorted(item["instruments"]) == sorted(INSTRUMENTS)


def test_run_backtest_returns_metrics_and_equity_curve() -> None:
    client, _ = make_client()
    with client:
        factor_hash = _promoted_factor_hash(client)
        response = client.post(
            "/v1/backtests",
            headers=headers(),
            json={"factor_ir_hash": factor_hash, "reason": "run backtest"},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["factor_ir_hash"] == factor_hash
        assert sorted(result["instrument_ids"]) == sorted(INSTRUMENTS)
        assert result["gross_of_fees"] is True
        assert result["metrics"]["total_return"] > 0  # 上涨行情 + 动量做多
        assert result["metrics"]["trade_count"] >= 1
        assert len(result["equity_curve"]) == 10
        assert result["start"] == "2026-08-01" and result["end"] == "2026-08-10"
        assert result["trades"], "应返回逐笔成交"
        assert result["trades"][0]["side"] in ("BUY", "SELL")
        assert "positions" in result
        assert len(result["backtest_hash"]) == 64

        # 只选一个标的 + 限定窗口 + 手数
        single = client.post(
            "/v1/backtests",
            headers=headers(),
            json={
                "factor_ir_hash": factor_hash,
                "instrument_ids": ["RB2610.SHF"],
                "start_date": "2026-08-03",
                "end_date": "2026-08-07",
                "lot_size": 2,
                "reason": "run backtest",
            },
        )
        assert single.status_code == 200
        body = single.json()
        assert body["instrument_ids"] == ["RB2610.SHF"]
        assert body["lot_size"] == 2
        assert body["start"] == "2026-08-03" and body["end"] == "2026-08-07"
        assert len(body["equity_curve"]) == 5


def test_backtest_rejects_unknown_factor() -> None:
    client, _ = make_client()
    with client:
        response = client.post(
            "/v1/backtests",
            headers=headers(),
            json={"factor_ir_hash": "0" * 64, "reason": "run backtest"},
        )
        assert response.status_code == 404


def _seed_realtime_rows(engine: Engine) -> None:
    """往 pit_observations 预置 10 天日线 + 最后 2 天 5m 分钟线。"""
    from sqlalchemy.orm import sessionmaker

    from quant_platform.data_gateway.loader import RawPITRow
    from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore

    rows: list[RawPITRow] = []
    ingested = START + timedelta(days=11)
    for day in range(10):
        ts = START + timedelta(days=day)
        for index, instrument in enumerate(INSTRUMENTS):
            close = 3000.0 + index * 1000.0 + day * 10.0
            rows.append(
                RawPITRow(
                    source_id="ifind-cn",
                    dataset_id="market-eod",
                    field="market.eod.close",
                    instrument_id=instrument,
                    event_time=ts,
                    available_time=ts.replace(minute=20),
                    ingested_at=ingested,
                    revision_id="rt-1",
                    license_tag="formal",
                    value_type="decimal",
                    value=str(close),
                )
            )
    # 最后两天各 3 根 5m bar（仅 close）
    for day in (8, 9):
        for bar_index in range(3):
            ts = (
                START
                + timedelta(days=day)
                - timedelta(minutes=60)
                + timedelta(minutes=5 * bar_index)
            )
            rows.append(
                RawPITRow(
                    source_id="akshare-cn",
                    dataset_id="market-minute",
                    field="market.minute.close",
                    instrument_id="RB2610.SHF",
                    event_time=ts,
                    available_time=ts,
                    ingested_at=ingested,
                    revision_id="rt-1",
                    license_tag="exploratory",
                    value_type="decimal",
                    value=str(3080.0 + bar_index),
                )
            )
    SqlAlchemyPitStore(sessionmaker(engine)).persist(rows)


def test_realtime_backtest_uses_ingested_data() -> None:
    client, engine = make_client()
    with client:
        factor_hash = _promoted_factor_hash(client)
        _seed_realtime_rows(engine)

        response = client.post(
            "/v1/backtests",
            headers=headers(),
            json={
                "factor_ir_hash": factor_hash,
                "data_source": "realtime",
                "reason": "run realtime backtest",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["data_source"] == "realtime"
        assert result["artifact_class"] == "FORMAL"
        assert result["metrics"]["total_return"] > 0  # 重算动量在上涨行情做多
        assert len(result["equity_curve"]) == 10

        coverage = client.get(
            "/v1/market-data/coverage?instruments=RB2610.SHF,AU2612.SHF",
            headers=headers(),
        )
        assert coverage.status_code == 200
        items = coverage.json()["items"]
        assert any(
            item["field_prefix"] == "market.eod" and item["row_count"] == 10
            for item in items
        )
        assert any(
            item["field_prefix"] == "market.minute"
            and item["artifact_class"] == "EXPLORATORY"
            for item in items
        )


def test_realtime_minute_frequency() -> None:
    client, engine = make_client()
    with client:
        factor_hash = _promoted_factor_hash(client)
        _seed_realtime_rows(engine)

        response = client.post(
            "/v1/backtests",
            headers=headers(),
            json={
                "factor_ir_hash": factor_hash,
                "instrument_ids": ["RB2610.SHF"],
                "data_source": "realtime",
                "frequency": "5m",
                "start_date": "2026-08-09",
                "end_date": "2026-08-10",
                "reason": "run 5m backtest",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["frequency"] == "5m"
        assert result["start"] == "2026-08-09"
        assert len(result["equity_curve"]) == 2  # 按日聚合


def test_realtime_without_ingested_data_fails() -> None:
    client, _engine = make_client()
    with client:
        factor_hash = _promoted_factor_hash(client)
        response = client.post(
            "/v1/backtests",
            headers=headers(),
            json={
                "factor_ir_hash": factor_hash,
                "data_source": "realtime",
                "reason": "no data ingested",
            },
        )
        assert response.status_code == 422
        assert "MARKET_DATA_NOT_INGESTED" in response.json()["code"]


def test_unknown_data_source_rejected() -> None:
    client, _engine = make_client()
    with client:
        factor_hash = _promoted_factor_hash(client)
        response = client.post(
            "/v1/backtests",
            headers=headers(),
            json={
                "factor_ir_hash": factor_hash,
                "data_source": "bogus",
                "reason": "bad source",
            },
        )
        assert response.status_code == 422
