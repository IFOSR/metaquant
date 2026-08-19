"""API tests for the train/infer execution endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.api.app import create_app
from quant_platform.artifacts.store import InMemoryArtifactStore
from quant_platform.factor_construction.artifacts import build_code_bundle, bundle_hash
from quant_platform.factor_construction.repository import (
    SqlAlchemyFactorConstructionRepository,
)
from quant_platform.factor_construction.service import FactorBuildService
from quant_platform.factor_construction.spec import FactorBuildSpec
from quant_platform.research.api import ResearchGrant, ResearchPrincipal
from quant_platform.research.models import Base
from quant_platform.research.repository import SqlAlchemyResearchRepository

_MODEL = b"""def build_model(hyperparams: dict):
    return None
"""

_TRAIN = b"""import numpy as np

def train(data, labels, spec):
    return {"coef": [1.0] * data.data.shape[1]}
"""

_INFER = b"""import numpy as np

def infer(data, weights):
    return (data.data.values @ np.array(weights["coef"])).tolist()
"""

_FILES = {"model.py": _MODEL, "train.py": _TRAIN, "infer.py": _INFER}

_SPEC = {
    "factor_id": "cn_a.demo_linear",
    "factor_name": "DemoLinear",
    "market": "CN_A",
    "universe_ref": "u",
    "inputs": ["a", "b"],
    "label": {"name": "future_return", "price_field": "a", "horizon": 1},
    "architecture": "LINEAR",
}

_FEATURES = [
    {"instrument_id": "A", "event_time": "2026-08-01T07:00:00Z", "a": 1.0, "b": 2.0},
    {"instrument_id": "B", "event_time": "2026-08-01T07:00:00Z", "a": 3.0, "b": 4.0},
]

_LABELS = [
    {"instrument_id": "A", "event_time": "2026-08-01T07:00:00Z", "label": 0.05},
    {"instrument_id": "B", "event_time": "2026-08-01T07:00:00Z", "label": -0.03},
]


class _FakeData:
    def pit_frame(
        self, *, instrument_ids, fields, decision_time, field_prefix="market.eod."
    ):
        return {"rows": _FEATURES}

    def label_frame(
        self,
        *,
        instrument_ids,
        price_field,
        horizon,
        decision_time,
        field_prefix="market.eod.",
        return_type="simple",
    ):
        return {"rows": _LABELS}


def make_client() -> tuple[TestClient, str, str]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    repository = SqlAlchemyFactorConstructionRepository(engine)
    artifacts = InMemoryArtifactStore()
    service = FactorBuildService(repository, artifacts, _FakeData())  # type: ignore[arg-type]

    def provider(token: str) -> ResearchPrincipal | None:
        if token != "test-researcher":
            return None
        caps = [
            "factor_construction.specs.write",
            "factor_construction.specs.freeze",
            "factor_construction.bundles.generate",
            "factor_construction.train",
        ]
        return ResearchPrincipal(
            actor_id="researcher-1",
            grants=frozenset(
                ResearchGrant(capability=cap, project_id="local", market="CN_A")
                for cap in caps
            ),
        )

    app = create_app(
        readiness_probe=lambda: {"postgres": True, "minio": True},
        research_repository=SqlAlchemyResearchRepository(engine),
        factor_construction_repository=repository,
        factor_build_service=service,
        research_principal_provider=provider,
    )
    client = TestClient(app)

    record = repository.create_spec(
        actor_id="researcher-1", spec=FactorBuildSpec.model_validate(_SPEC)
    )
    repository.freeze_spec(
        spec_id=record.id, actor_id="researcher-1", expected_resource_version=1
    )
    manifest = build_code_bundle(_FILES, spec_hash=record.spec_hash)
    repository.create_bundle(
        actor_id="researcher-1",
        spec_hash=record.spec_hash,
        bundle_hash=bundle_hash(manifest),
        manifest=manifest,
        files=_FILES,
        artifact_store=artifacts,
    )
    return client, record.spec_hash, bundle_hash(manifest)


def test_train_endpoint() -> None:
    client, spec_hash, bundle = make_client()
    response = client.post(
        "/v1/factor-build-specs:train",
        json={
            "metadata": _metadata(),
            "spec_hash": spec_hash,
            "bundle_hash": bundle,
            "instrument_ids": ["A", "B"],
            "decision_time": "2026-08-02T07:00:00Z",
        },
        headers=_auth(),
    )
    assert response.status_code == 202
    assert response.json()["weights_hash"].startswith("sha256:")
    run = response.json()["run"]
    assert run["state"] == "SUCCEEDED"


def _auth() -> dict[str, str]:
    return {
        "Authorization": "Bearer test-researcher",
        "Idempotency-Key": "test-idempotency-key-0001",
    }


def _metadata() -> dict[str, object]:
    return {
        "reason": "Train a demo linear factor",
        "parent_artifact_id": None,
        "budget": {
            "candidate_limit": 1,
            "llm_token_limit": 1000,
            "cpu_hours": 1,
            "wall_clock_minutes": 30,
        },
        "schema_version": "1.0",
    }
