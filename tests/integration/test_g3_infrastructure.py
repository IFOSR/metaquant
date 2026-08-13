from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from minio import Minio
from sqlalchemy import Engine, create_engine, func, select

from quant_platform.api.app import create_app
from quant_platform.artifacts import MinioArtifactStore, canonical_bytes, content_hash
from quant_platform.experiment_runtime import (
    ExecutionIdentity,
    InMemoryFormalSnapshotCatalog,
)
from quant_platform.experiment_runtime.repository import (
    SqlAlchemyExperimentRepository,
)
from quant_platform.research.models import (
    ExperimentArtifactModel,
    ExperimentAttemptModel,
    ExperimentCommandReceiptModel,
    ExperimentLineageModel,
    ExperimentRunModel,
    FactorValidationModel,
)
from quant_platform.research.repository import SqlAlchemyResearchRepository
from quant_platform.validation import (
    FormalLabelSnapshot,
    ForwardReturnLabel,
    ICSign,
    InMemoryLabelSnapshotCatalog,
    InMemoryValidationPolicyCatalog,
    LabelSnapshotRow,
    ValidationPolicy,
)
from tests.experiment_support import (
    at,
    create_frozen_brief,
    headers,
    metadata,
    preregister_command,
    provider,
    run_command,
    snapshot,
)

pytestmark = pytest.mark.integration


def _database_url() -> str:
    value = os.getenv("G3_TEST_DATABASE_URL")
    if value is None:
        pytest.skip("G3_TEST_DATABASE_URL is required")
    return value


def _minio_endpoint() -> str:
    value = os.getenv("G3_TEST_MINIO_ENDPOINT")
    if value is None:
        pytest.skip("G3_TEST_MINIO_ENDPOINT is required")
    return value


def test_minio_content_address_round_trip() -> None:
    store = MinioArtifactStore(
        Minio(
            _minio_endpoint(),
            access_key="quant_minio",
            secret_key="quant_minio_dev",
            secure=False,
        ),
        bucket="artifacts",
    )
    payload = canonical_bytes(
        {
            "schema_version": "g3-minio-roundtrip/v1",
            "market": "CN_A",
            "values": [1, 2, 3],
        }
    )

    manifest = store.put(payload, media_type="application/json")

    assert manifest.content_hash == content_hash(payload)
    assert store.exists(manifest.content_hash)
    assert store.get(manifest.content_hash) == payload
    assert store.verify(manifest)


def test_postgres_concurrent_identical_fingerprints_create_one_run() -> None:
    engine = create_engine(_database_url(), pool_pre_ping=True)
    research = SqlAlchemyResearchRepository(engine)
    experiments = SqlAlchemyExperimentRepository(
        engine,
        research_repository=research,
        artifact_store=MinioArtifactStore(
            Minio(
                _minio_endpoint(),
                access_key="quant_minio",
                secret_key="quant_minio_dev",
                secure=False,
            ),
            bucket="artifacts",
        ),
        snapshot_catalog=InMemoryFormalSnapshotCatalog((snapshot(),)),
        execution_identity=ExecutionIdentity(
            code_sha="a" * 40,
            image_digest="sha256:" + "b" * 64,
            dependency_lock_hash="c" * 64,
            executor_version="factor-executor/v1",
            config_hash="d" * 64,
        ),
    )
    app = create_app(
        readiness_probe=lambda: {"postgres": True, "minio": True},
        research_repository=research,
        experiment_repository=experiments,
        research_principal_provider=provider,
    )
    with TestClient(app) as client:
        job_id, brief_id = create_frozen_brief(client)
        registered = client.post(
            "/v1/experiments:preregister",
            headers=headers("g3-pg-preregister-0001"),
            json=preregister_command(job_id, brief_id),
        )
        registered.raise_for_status()
        experiment_id = registered.json()["resource_id"]

    def execute(key: str) -> tuple[int, dict[str, object]]:
        with TestClient(app) as client:
            response = client.post(
                f"/v1/experiments/{experiment_id}:run",
                headers=headers(key, '"1"'),
                json=run_command(),
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                execute,
                ("g3-pg-concurrent-run-0001", "g3-pg-concurrent-run-0002"),
            )
        )

    assert {status for status, _ in results} == {202}
    assert len({body["resource_id"] for _, body in results}) == 1
    with engine.connect() as connection:
        assert (
            connection.scalar(select(func.count()).select_from(ExperimentRunModel)) == 1
        )
        assert (
            connection.scalar(select(func.count()).select_from(ExperimentAttemptModel))
            == 1
        )
        assert (
            connection.scalar(select(func.count()).select_from(ExperimentArtifactModel))
            == 2
        )
        assert (
            connection.scalar(select(func.count()).select_from(ExperimentLineageModel))
            == 1
        )
        assert (
            connection.scalar(
                select(func.count()).select_from(ExperimentCommandReceiptModel)
            )
            == 3
        )


def label_snapshot() -> FormalLabelSnapshot:
    return FormalLabelSnapshot(
        snapshot_id="label-snapshot-cn-a-001",
        label=ForwardReturnLabel(
            label_id="label.cn_a.forward_5d",
            market="CN_A",
            horizon=5,
            field_ref="market.eod.forward_return_5d",
        ),
        rows=(
            LabelSnapshotRow(
                instrument_id="600000.SSE",
                event_time=datetime.fromisoformat(at(2)),
                available_time=datetime.fromisoformat(at(12)),
                value=0.2,
            ),
        ),
    )


def _validation_repository(engine: Engine) -> SqlAlchemyExperimentRepository:
    policy = ValidationPolicy(
        policy_id="policy://cn-a-daily-factor/v1",
        market="CN_A",
        min_coverage=0.0,
        min_observations=1,
        max_constant_ratio=1.0,
        ic_sign=ICSign.ANY,
        min_icir=0.0,
        min_nw_t=0.0,
        quantile_count=2,
        decay_horizons=(5,),
    )
    return SqlAlchemyExperimentRepository(
        engine,
        research_repository=SqlAlchemyResearchRepository(engine),
        artifact_store=MinioArtifactStore(
            Minio(
                _minio_endpoint(),
                access_key="quant_minio",
                secret_key="quant_minio_dev",
                secure=False,
            ),
            bucket="artifacts",
        ),
        snapshot_catalog=InMemoryFormalSnapshotCatalog((snapshot(),)),
        execution_identity=ExecutionIdentity(
            code_sha="a" * 40,
            image_digest="sha256:" + "b" * 64,
            dependency_lock_hash="c" * 64,
            executor_version="factor-executor/v1",
            config_hash="d" * 64,
        ),
        policy_catalog=InMemoryValidationPolicyCatalog((policy,)),
        label_snapshot_catalog=InMemoryLabelSnapshotCatalog((label_snapshot(),)),
    )


def test_postgres_validate_command_stores_report_and_lineage() -> None:
    engine = create_engine(_database_url(), pool_pre_ping=True)
    experiments = _validation_repository(engine)
    app = create_app(
        readiness_probe=lambda: {"postgres": True, "minio": True},
        research_repository=experiments._research,
        experiment_repository=experiments,
        research_principal_provider=provider,
    )
    with TestClient(app) as client:
        job_id, brief_id = create_frozen_brief(client)
        registered = client.post(
            "/v1/experiments:preregister",
            headers=headers("g3-pg-validate-preregister-0001"),
            json=preregister_command(job_id, brief_id),
        )
        registered.raise_for_status()
        experiment_id = registered.json()["resource_id"]
        run_response = client.post(
            f"/v1/experiments/{experiment_id}:run",
            headers=headers("g3-pg-validate-run-0001", '"1"'),
            json=run_command(),
        )
        run_response.raise_for_status()
        run_id = run_response.json()["resource_id"]

        with engine.connect() as connection:
            lineage_before = (
                connection.scalar(
                    select(func.count()).select_from(ExperimentLineageModel)
                )
                or 0
            )
            validation_before = (
                connection.scalar(
                    select(func.count()).select_from(FactorValidationModel)
                )
                or 0
            )

        label_snap = label_snapshot()
        validated = client.post(
            f"/v1/experiment-runs/{run_id}:validate",
            headers=headers("g3-pg-validate-0001"),
            json={
                "metadata": metadata("Validate factor"),
                "policy_id": "policy://cn-a-daily-factor/v1",
                "label_snapshot_id": label_snap.snapshot_id,
                "label_snapshot_manifest_hash": label_snap.content_hash(),
            },
        )
        validated.raise_for_status()

        with engine.connect() as connection:
            lineage_after = (
                connection.scalar(
                    select(func.count()).select_from(ExperimentLineageModel)
                )
                or 0
            )
            validation_after = (
                connection.scalar(
                    select(func.count()).select_from(FactorValidationModel)
                )
                or 0
            )

    assert lineage_after == lineage_before + 1
    assert validation_after == validation_before + 1
