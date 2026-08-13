from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from minio import Minio
from sqlalchemy import create_engine, func, select

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
