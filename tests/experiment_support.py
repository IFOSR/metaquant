from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from quant_platform.experiments import canonical_hash
from quant_platform.research.api import ResearchGrant, ResearchPrincipal


def at(day: int, hour: int = 15) -> str:
    return datetime(2026, 8, day, hour, tzinfo=UTC).isoformat()


def provider(token: str) -> ResearchPrincipal | None:
    if token != "experimenter":
        return None
    grants = {
        ResearchGrant(name, "local", market)
        for market in ("CN_A", "CN_COMMODITY_FUTURES")
        for name in (
            "research.jobs.manage",
            "research.experiments.read",
            "research.experiments.preregister",
            "research.experiments.run",
        )
    }
    return ResearchPrincipal(actor_id="experimenter-1", grants=frozenset(grants))


def headers(key: str | None = None, etag: str | None = None) -> dict[str, str]:
    result = {"Authorization": "Bearer experimenter"}
    if key:
        result["Idempotency-Key"] = key
    if etag:
        result["If-Match"] = etag
    return result


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


def factor_ir() -> dict[str, object]:
    return {
        "schema_version": "factor-ir/v1",
        "factor_id": "classic.cn_a.momentum_1d",
        "version": "1.0.0",
        "market_scope": {
            "market": "CN_A",
            "frequency": "1d",
            "universe_ref": "universe://csi300-pit/v1",
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
            "params": {"periods": 1},
        },
        "validation_policy_ref": "policy://cn-a-daily-factor/v1",
    }


def snapshot() -> dict[str, object]:
    return {
        "snapshot_id": "snapshot-cn-a-001",
        "frozen_at": at(12),
        "sealed": True,
        "artifact_class": "FORMAL",
        "market": "CN_A",
        "universe_ref": "universe://csi300-pit/v1",
        "frequency": "1d",
        "decision_clock": "T_CLOSE+30m",
        "trade_clock": "T+1_OPEN",
        "purpose": "RESEARCH",
        "allowed_license_tags": ["licensed-research"],
        "datasets": [
            {
                "dataset_id": "market-eod",
                "source_id": "licensed-source",
                "source_class": "FORMAL",
                "fields": [
                    {
                        "name": "market.eod.close_adjusted",
                        "value_type": "decimal",
                        "unit": "CNY",
                        "license_tag": "licensed-research",
                        "allowed_purposes": ["RESEARCH"],
                    },
                    {
                        "name": "future_sentinel",
                        "value_type": "decimal",
                        "unit": "1",
                        "license_tag": "licensed-research",
                        "allowed_purposes": ["RESEARCH"],
                    },
                ],
            }
        ],
        "rows": [
            {
                "dataset_id": "market-eod",
                "field": "market.eod.close_adjusted",
                "instrument_id": "600000.SSE",
                "event_time": at(1),
                "available_time": at(1, 15),
                "ingested_at": at(1, 15),
                "revision_id": "r1",
                "source_id": "licensed-source",
                "license_tag": "licensed-research",
                "value": 10,
            },
            {
                "dataset_id": "market-eod",
                "field": "market.eod.close_adjusted",
                "instrument_id": "600000.SSE",
                "event_time": at(2),
                "available_time": at(2, 15),
                "ingested_at": at(2, 15),
                "revision_id": "r1",
                "source_id": "licensed-source",
                "license_tag": "licensed-research",
                "value": 12,
            },
            {
                "dataset_id": "market-eod",
                "field": "market.eod.close_adjusted",
                "instrument_id": "600000.SSE",
                "event_time": at(9),
                "available_time": at(11),
                "ingested_at": at(11),
                "revision_id": "future",
                "source_id": "licensed-source",
                "license_tag": "licensed-research",
                "value": -999999,
            },
            {
                "dataset_id": "market-eod",
                "field": "future_sentinel",
                "instrument_id": "600000.SSE",
                "event_time": at(2),
                "available_time": at(2),
                "ingested_at": at(2),
                "revision_id": "sentinel",
                "source_id": "licensed-source",
                "license_tag": "licensed-research",
                "value": 999999,
            },
        ],
    }


def preregister_command(job_id: str, brief_id: str) -> dict[str, object]:
    formal_snapshot = snapshot()
    return {
        "metadata": metadata("Preregister deterministic factor experiment"),
        "research_job_id": job_id,
        "brief_version_id": brief_id,
        "decision_time": at(5, 16),
        "random_seed": 41,
        "resource_budget": {
            "cpu_seconds": 300,
            "wall_clock_seconds": 600,
            "memory_mb": 2048,
            "max_observations": 10000,
        },
        "factor_ir": factor_ir(),
        "snapshot_id": formal_snapshot["snapshot_id"],
        "snapshot_manifest_hash": canonical_hash(formal_snapshot),
    }


def run_command() -> dict[str, object]:
    return {
        "metadata": metadata("Run deterministic factor experiment"),
    }


def create_frozen_brief(client: TestClient) -> tuple[str, str]:
    created = client.post(
        "/v1/research-jobs",
        headers=headers("create-job-experiment-001"),
        json={
            "metadata": metadata("Create experiment research job"),
            "market": "CN_A",
            "universe_ref": "universe://csi300-pit/v1",
            "frequency": "1d",
            "decision_clock": "T_CLOSE+30m",
            "trade_clock": "T+1_OPEN",
            "horizon": "20TD",
            "research_brief_version_id": "brief://seed",
        },
    )
    job_id = created.json()["resource_id"]
    brief = client.post(
        f"/v1/research-jobs/{job_id}/brief-versions",
        headers=headers("create-brief-experiment-001", '"1"'),
        json={
            "metadata": metadata("Create experiment research brief"),
            "brief": {
                "hypothesis": "Medium-term price momentum persists.",
                "economic_mechanism": "Information diffuses slowly.",
                "expected_direction": "POSITIVE",
                "falsification_conditions": ["Coverage falls below threshold"],
                "allowed_data_domains": ["formal.market.eod"],
                "forbidden_data_domains": ["future.revisions"],
                "constraints": ["daily only"],
                "evidence_ref_ids": ["evidence://momentum/1"],
                "uncertainties": ["corporate action timing"],
            },
        },
    )
    brief_id = brief.json()["resource_id"]
    frozen = client.post(
        f"/v1/research-brief-versions/{brief_id}:freeze",
        headers=headers("freeze-brief-experiment-001", '"1"'),
        json=metadata("Freeze experiment research brief"),
    )
    assert frozen.status_code == 202
    return job_id, brief_id
