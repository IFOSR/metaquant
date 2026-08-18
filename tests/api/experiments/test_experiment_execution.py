from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Never

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
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
from quant_platform.research.api import ResearchGrant, ResearchPrincipal
from quant_platform.research.models import (
    AuditEventModel,
    Base,
    ExperimentArtifactModel,
    ExperimentAttemptModel,
    ExperimentCommandReceiptModel,
    ExperimentLineageModel,
    ExperimentRunModel,
    OutboxEventModel,
)
from quant_platform.research.repository import SqlAlchemyResearchRepository
from tests.experiment_support import (
    create_frozen_brief,
    headers,
    preregister_command,
    provider,
    run_command,
    snapshot,
)

EXECUTION_IDENTITY = ExecutionIdentity(
    code_sha="a" * 40,
    image_digest="sha256:" + "b" * 64,
    dependency_lock_hash="c" * 64,
    executor_version="factor-executor/v1",
    config_hash="d" * 64,
)


def make_stack(
    principal_provider: Callable[[str], ResearchPrincipal | None] = provider,
) -> tuple[TestClient, Engine, SqlAlchemyResearchRepository]:
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
        snapshot_catalog=InMemoryFormalSnapshotCatalog((snapshot(),)),
        execution_identity=EXECUTION_IDENTITY,
    )
    client = TestClient(
        create_app(
            readiness_probe=lambda: {"postgres": True, "minio": True},
            research_repository=research,
            experiment_repository=experiments,
            research_principal_provider=principal_provider,
        )
    )
    return client, engine, research


def make_client(
    principal_provider: Callable[[str], ResearchPrincipal | None] = provider,
) -> TestClient:
    return make_stack(principal_provider)[0]


def client_with_experiment_repository(
    repository: SqlAlchemyExperimentRepository,
    research: SqlAlchemyResearchRepository,
) -> TestClient:
    return TestClient(
        create_app(
            readiness_probe=lambda: {"postgres": True, "minio": True},
            research_repository=research,
            experiment_repository=repository,
            research_principal_provider=provider,
        )
    )


def table_count(engine: Engine, model: type[Any]) -> int:
    with engine.connect() as connection:
        return int(connection.scalar(select(func.count()).select_from(model)) or 0)


def test_preregister_run_and_artifact_lineage_are_auditable_and_idempotent() -> None:
    client = make_client()
    job_id, brief_id = create_frozen_brief(client)
    preregistration = preregister_command(job_id, brief_id)
    first = client.post(
        "/v1/experiments:preregister",
        headers=headers("preregister-experiment-001"),
        json=preregistration,
    )
    replay = client.post(
        "/v1/experiments:preregister",
        headers=headers("preregister-experiment-001"),
        json=preregistration,
    )

    assert first.status_code == replay.status_code == 202
    assert first.json() == replay.json()
    experiment_id = first.json()["resource_id"]
    job_snapshot = client.get(f"/v1/research-jobs/{job_id}", headers=headers())
    assert job_snapshot.json()["experiment_id"] == experiment_id
    spec = client.get(f"/v1/experiments/{experiment_id}", headers=headers())
    assert spec.status_code == 200
    assert spec.json()["state"] == "PREREGISTERED"
    assert spec.json()["factor_ir_hash"]
    assert spec.json()["snapshot_manifest_hash"]
    assert spec.json()["factor_ir"]["factor_id"]
    assert spec.json()["factor_ir"]["expression"]
    assert datetime.fromisoformat(
        spec.json()["decision_time"].replace("Z", "+00:00")
    ) == datetime.fromisoformat(preregistration["decision_time"])
    assert spec.json()["random_seed"] == preregistration["random_seed"]

    execution = run_command()
    run = client.post(
        f"/v1/experiments/{experiment_id}:run",
        headers=headers("run-experiment-000001", '"1"'),
        json=execution,
    )
    run_replay = client.post(
        f"/v1/experiments/{experiment_id}:run",
        headers=headers("run-experiment-000001", '"1"'),
        json=execution,
    )

    assert run.status_code == run_replay.status_code == 202
    assert run.json() == run_replay.json()
    run_id = run.json()["resource_id"]
    updated_spec = client.get(f"/v1/experiments/{experiment_id}", headers=headers())
    assert updated_spec.json()["latest_run_id"] == run_id
    run_snapshot = client.get(f"/v1/experiment-runs/{run_id}", headers=headers())
    assert run_snapshot.status_code == 200
    assert run_snapshot.json()["state"] == "SUCCEEDED"
    assert run_snapshot.json()["attempt_count"] == 1
    assert run_snapshot.json()["validation_summary"]["observation_count"] == 2
    assert run_snapshot.json()["validation_summary"]["coverage_ratio"] == 0.5
    assert run_snapshot.json()["invariance"]["future_truncation_passed"] is True
    assert run_snapshot.json()["invariance"]["sentinel_isolation_passed"] is True

    artifacts = client.get(
        f"/v1/experiment-runs/{run_id}/artifacts",
        headers=headers(),
    )
    assert artifacts.status_code == 200
    assert {item["artifact_type"] for item in artifacts.json()["items"]} == {
        "FactorComputationArtifact",
        "ValidationArtifact",
    }
    assert len(artifacts.json()["lineage"]) == 1


def test_same_fingerprint_with_new_key_reuses_run_and_persists_receipt() -> None:
    client, engine, _ = make_stack()
    job_id, brief_id = create_frozen_brief(client)
    preregistered = client.post(
        "/v1/experiments:preregister",
        headers=headers("preregister-experiment-reuse"),
        json=preregister_command(job_id, brief_id),
    )
    experiment_id = preregistered.json()["resource_id"]

    first = client.post(
        f"/v1/experiments/{experiment_id}:run",
        headers=headers("run-experiment-reuse-001", '"1"'),
        json=run_command(),
    )
    reused = client.post(
        f"/v1/experiments/{experiment_id}:run",
        headers=headers("run-experiment-reuse-002", '"1"'),
        json=run_command(),
    )
    replay = client.post(
        f"/v1/experiments/{experiment_id}:run",
        headers=headers("run-experiment-reuse-002", '"1"'),
        json=run_command(),
    )

    assert first.status_code == reused.status_code == replay.status_code == 202
    assert reused.json() == replay.json()
    assert reused.json()["resource_id"] == first.json()["resource_id"]
    assert table_count(engine, ExperimentRunModel) == 1
    assert table_count(engine, ExperimentAttemptModel) == 1
    assert table_count(engine, ExperimentArtifactModel) == 2
    assert table_count(engine, ExperimentLineageModel) == 1
    assert table_count(engine, ExperimentCommandReceiptModel) == 3
    assert table_count(engine, AuditEventModel) == 6
    assert table_count(engine, OutboxEventModel) == 6


def test_run_transaction_rolls_back_all_metadata_on_failure() -> None:
    client, engine, research = make_stack()
    job_id, brief_id = create_frozen_brief(client)
    preregistered = client.post(
        "/v1/experiments:preregister",
        headers=headers("preregister-experiment-rollback"),
        json=preregister_command(job_id, brief_id),
    )
    experiment_id = preregistered.json()["resource_id"]
    baseline_audits = table_count(engine, AuditEventModel)
    baseline_outbox = table_count(engine, OutboxEventModel)
    baseline_receipts = table_count(engine, ExperimentCommandReceiptModel)

    def failure() -> Never:
        raise RuntimeError("injected experiment transaction failure")

    failing = SqlAlchemyExperimentRepository(
        engine,
        research_repository=research,
        artifact_store=InMemoryArtifactStore(),
        snapshot_catalog=InMemoryFormalSnapshotCatalog((snapshot(),)),
        execution_identity=EXECUTION_IDENTITY,
        before_commit=failure,
    )
    failing_client = client_with_experiment_repository(failing, research)

    with pytest.raises(RuntimeError, match="injected experiment transaction failure"):
        failing_client.post(
            f"/v1/experiments/{experiment_id}:run",
            headers=headers("run-experiment-rollback-001", '"1"'),
            json=run_command(),
        )

    assert table_count(engine, ExperimentRunModel) == 0
    assert table_count(engine, ExperimentAttemptModel) == 0
    assert table_count(engine, ExperimentArtifactModel) == 0
    assert table_count(engine, ExperimentLineageModel) == 0
    assert table_count(engine, ExperimentCommandReceiptModel) == baseline_receipts
    assert table_count(engine, AuditEventModel) == baseline_audits
    assert table_count(engine, OutboxEventModel) == baseline_outbox


def test_experiment_access_is_safe_404_for_wrong_market_scope() -> None:
    client = make_client(
        lambda token: ResearchPrincipal(
            actor_id="cn-a",
            grants=frozenset(
                {
                    ResearchGrant(
                        "research.experiments.read",
                        "local",
                        "CN_A",
                    )
                }
            ),
        )
        if token == "limited"
        else provider(token)
    )
    hidden = client.get(
        "/v1/experiments/experiment-missing",
        headers={"Authorization": "Bearer limited"},
    )
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "RESOURCE_NOT_FOUND"


def test_preregister_rejects_unknown_or_hash_mismatched_formal_snapshot() -> None:
    client = make_client()
    job_id, brief_id = create_frozen_brief(client)
    unknown = preregister_command(job_id, brief_id)
    unknown["snapshot_id"] = "snapshot-not-registered"

    missing = client.post(
        "/v1/experiments:preregister",
        headers=headers("preregister-unknown-snapshot"),
        json=unknown,
    )
    mismatched = preregister_command(job_id, brief_id)
    mismatched["snapshot_manifest_hash"] = "0" * 64
    wrong_hash = client.post(
        "/v1/experiments:preregister",
        headers=headers("preregister-wrong-snapshot-hash"),
        json=mismatched,
    )

    assert missing.status_code == 422
    assert missing.json()["code"] == "FORMAL_SNAPSHOT_NOT_REGISTERED"
    assert wrong_hash.status_code == 422
    assert wrong_hash.json()["code"] == "SNAPSHOT_MANIFEST_HASH_MISMATCH"


def test_run_requires_matching_if_match_and_rejects_client_execution_identity() -> None:
    client = make_client()
    job_id, brief_id = create_frozen_brief(client)
    preregistered = client.post(
        "/v1/experiments:preregister",
        headers=headers("preregister-run-precondition"),
        json=preregister_command(job_id, brief_id),
    )
    experiment_id = preregistered.json()["resource_id"]

    missing = client.post(
        f"/v1/experiments/{experiment_id}:run",
        headers=headers("run-without-if-match"),
        json=run_command(),
    )
    stale = client.post(
        f"/v1/experiments/{experiment_id}:run",
        headers=headers("run-stale-if-match", '"2"'),
        json=run_command(),
    )
    injected = client.post(
        f"/v1/experiments/{experiment_id}:run",
        headers=headers("run-client-identity", '"1"'),
        json={**run_command(), "code_sha": "f" * 40},
    )

    assert missing.status_code == 428
    assert missing.json()["code"] == "PRECONDITION_REQUIRED"
    assert stale.status_code == 412
    assert stale.json()["code"] == "RESOURCE_VERSION_MISMATCH"
    assert injected.status_code == 422


def test_run_fails_closed_when_ir_references_sentinel_field() -> None:
    client = make_client()
    job_id, brief_id = create_frozen_brief(client)
    preregistration = preregister_command(job_id, brief_id)
    # Point the IR at the injected sentinel field; the invariance check must
    # fail the run instead of merely recording the violation.
    factor_ir = preregistration["factor_ir"]
    assert isinstance(factor_ir, dict)
    factor_ir["inputs"] = [
        {
            "alias": "sentinel",
            "field_ref": "future_sentinel",
            "data_type": "ScalarSeries",
            "unit": "1",
            "available_time_rule": "T_CLOSE+20m",
        }
    ]
    factor_ir["expression"] = {
        "op": "returns",
        "args": [{"ref": "sentinel"}],
        "params": {"periods": 1},
    }
    preregistered = client.post(
        "/v1/experiments:preregister",
        headers=headers("preregister-sentinel-reference"),
        json=preregistration,
    )
    assert preregistered.status_code == 202
    experiment_id = preregistered.json()["resource_id"]

    run = client.post(
        f"/v1/experiments/{experiment_id}:run",
        headers=headers("run-sentinel-reference", '"1"'),
        json=run_command(),
    )
    assert run.status_code == 202
    run_id = run.json()["resource_id"]

    body = client.get(f"/v1/experiment-runs/{run_id}", headers=headers()).json()
    assert body["state"] == "FAILED"
    assert body["invariance"]["sentinel_isolation_passed"] is False


def test_formal_snapshots_listing_exposes_ids_and_manifest_hashes() -> None:
    client = make_client()

    response = client.get("/v1/formal-snapshots", headers=headers())

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["snapshot_id"] for item in items] == ["snapshot-cn-a-001"]
    assert items[0]["frequency"] == "1d"
    assert items[0]["market"] == "CN_A"
    assert len(items[0]["manifest_hash"]) == 64
