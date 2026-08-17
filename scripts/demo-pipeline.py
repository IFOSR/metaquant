"""演示完整研究流程（期货日频）：创建任务 → brief → 冻结 → 预注册 → 运行 →
验证 → 晋级。

在容器内运行（能 import 项目代码算 label hash），通过 host.docker.internal
访问宿主机的真实后端。

运行：
    docker compose run --rm --no-deps api python scripts/demo-pipeline.py
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from quant_platform.validation.label_snapshot import (
    FormalLabelSnapshot,
    ForwardReturnLabel,
    LabelSnapshotRow,
)

BASE = "http://host.docker.internal:8091"
TOKEN = "local-researcher"


def request(
    method: str,
    path: str,
    body: object | None = None,
    *,
    key: str | None = None,
    etag: str | None = None,
) -> dict:
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    if key:
        headers["Idempotency-Key"] = key
    if etag:
        headers["If-Match"] = etag
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        print(f"    [HTTP {exc.code}] {path}: {detail[:800]}")
        raise
    return payload


def metadata(reason: str) -> dict[str, object]:
    return {
        "reason": reason,
        "parent_artifact_id": None,
        "budget": {
            "candidate_limit": 1,
            "llm_token_limit": 0,
            "cpu_hours": 1,
            "wall_clock_minutes": 30,
        },
        "schema_version": "1.0",
    }


def load_label_hash() -> tuple[str, str]:
    doc = json.loads(Path("/app/config/label-snapshots.json").read_text())
    item = next(i for i in doc if i["label"]["market"] == "CN_COMMODITY_FUTURES")
    label_payload = item["label"]
    rows = tuple(
        LabelSnapshotRow(
            instrument_id=str(row["instrument_id"]),
            event_time=datetime.fromisoformat(str(row["event_time"])),
            available_time=datetime.fromisoformat(str(row["available_time"])),
            value=float(row["value"]) if row.get("value") is not None else None,
        )
        for row in item["rows"]
    )
    snapshot = FormalLabelSnapshot(
        snapshot_id=str(item["snapshot_id"]),
        label=ForwardReturnLabel(
            label_id=str(label_payload["label_id"]),
            market=str(label_payload["market"]),
            horizon=int(label_payload["horizon"]),
            field_ref=str(label_payload["field_ref"]),
            return_definition=str(
                label_payload.get("return_definition", "close_to_close")
            ),
        ),
        rows=rows,
    )
    return snapshot.snapshot_id, snapshot.content_hash()


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
        "validation_policy_ref": "policy://cn-futures-daily-factor/v1",
    }


def step(name: str) -> None:
    print(f"\n==> {name}")


def main() -> None:
    # 0. 拿快照 manifest hash
    snaps = request("GET", "/v1/formal-snapshots")["items"]
    fut_eod = next(
        s for s in snaps if s["snapshot_id"] == "snapshot-cn-futures-eod-001"
    )
    snap_hash = str(fut_eod["manifest_hash"])
    label_id, label_hash = load_label_hash()
    print(f"[快照] snapshot-cn-futures-eod-001 hash={snap_hash[:12]}…")
    print(f"[标签] {label_id} hash={label_hash[:12]}…")

    # 1. 创建期货研究任务
    step("1. 创建期货研究任务")
    job = request(
        "POST",
        "/v1/research-jobs",
        {
            "metadata": metadata("创建期货动量研究任务"),
            "market": "CN_COMMODITY_FUTURES",
            "environment": "RESEARCH",
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
        key=f"demo-job-{uuid4().hex[:8]}",
    )
    job_id = job["resource_id"]
    print(f"    任务 id: {job_id}")

    # 2. 创建 Brief
    step("2. 创建研究论点 Brief")
    brief = request(
        "POST",
        f"/v1/research-jobs/{job_id}/brief-versions",
        {
            "metadata": metadata("创建期货动量研究论点"),
            "brief": {
                "hypothesis": "螺纹钢和黄金的短期价格动量在未来 5 个交易日延续",
                "economic_mechanism": "商品价格信息扩散缓慢，动量效应在日频尺度持续",
                "expected_direction": "POSITIVE",
                "falsification_conditions": ["覆盖样本不足 2 个交易日"],
                "allowed_data_domains": ["formal.market.eod"],
                "forbidden_data_domains": ["future.revisions"],
                "constraints": ["daily only"],
                "evidence_ref_ids": ["evidence://futures-momentum/1"],
                "uncertainties": ["主力换月时点"],
            },
        },
        key=f"demo-brief-{uuid4().hex[:8]}",
        etag='"1"',
    )
    brief_id = brief["resource_id"]
    print(f"    brief id: {brief_id}")

    # 3. 冻结 Brief
    step("3. 冻结 Brief")
    frozen = request(
        "POST",
        f"/v1/research-brief-versions/{brief_id}:freeze",
        metadata("冻结研究论点"),
        key=f"demo-freeze-{uuid4().hex[:8]}",
        etag='"1"',
    )
    print(f"    冻结: {frozen['status']}")

    # 4. 预注册实验
    step("4. 预注册实验（因子 IR + 快照）")
    registered = request(
        "POST",
        "/v1/experiments:preregister",
        {
            "metadata": metadata("预注册期货动量因子实验"),
            "research_job_id": job_id,
            "brief_version_id": brief_id,
            "decision_time": "2026-08-05T16:00:00+00:00",
            "random_seed": 41,
            "resource_budget": {
                "cpu_seconds": 300,
                "wall_clock_seconds": 600,
                "memory_mb": 2048,
                "max_observations": 10000,
            },
            "factor_ir": futures_factor_ir(),
            "snapshot_id": "snapshot-cn-futures-eod-001",
            "snapshot_manifest_hash": snap_hash,
        },
        key=f"demo-preregister-{uuid4().hex[:8]}",
    )
    experiment_id = registered["resource_id"]
    print(f"    实验 id: {experiment_id}")

    # 5. 运行实验
    step("5. 运行实验（执行因子计算）")
    run = request(
        "POST",
        f"/v1/experiments/{experiment_id}:run",
        {"metadata": metadata("运行期货动量因子")},
        key=f"demo-run-{uuid4().hex[:8]}",
        etag='"1"',
    )
    run_id = run["resource_id"]
    print(f"    run id: {run_id}")

    # 6. 验证
    step("6. 验证（对标签快照）")
    validated = request(
        "POST",
        f"/v1/experiment-runs/{run_id}:validate",
        {
            "metadata": metadata("验证期货动量因子"),
            "policy_id": "policy://cn-futures-daily-factor/v1",
            "label_snapshot_id": label_id,
            "label_snapshot_manifest_hash": label_hash,
        },
        key=f"demo-validate-{uuid4().hex[:8]}",
    )
    print(f"    验证: {validated['status']}")

    report = request("GET", f"/v1/experiment-runs/{run_id}/validation")
    quality = report["data_quality"]
    print(
        f"    观察数: {quality['observation_count']}  "
        f"覆盖: {quality['coverage_ratio']:.2f}"
    )

    # 7. 晋级
    step("7. 晋级（进入双人审批）")
    promoted = request(
        "POST",
        f"/v1/experiment-runs/{run_id}:promote",
        {
            "metadata": metadata("晋级期货动量因子"),
            "policy_id": "policy://cn-futures-promotion/v1",
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
        key=f"demo-promote-{uuid4().hex[:8]}",
    )
    print(f"    晋级: {promoted['status']}")

    print("\n[完成] 研究流程跑通：任务 → brief → 冻结 → 预注册 → 运行 → 验证 → 晋级")
    print(f"  任务: {job_id}")
    print(f"  实验: {experiment_id}  run: {run_id}")


if __name__ == "__main__":
    main()
