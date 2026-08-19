"""API tests for the factor construction control plane."""

from __future__ import annotations

from collections.abc import Callable

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
from quant_platform.research.api import (
    ResearchGrant,
    ResearchPrincipal,
)
from quant_platform.research.models import Base
from quant_platform.research.repository import SqlAlchemyResearchRepository

_CAPS = [
    "factor_construction.specs.write",
    "factor_construction.specs.freeze",
    "factor_construction.bundles.generate",
]

_SPEC = {
    "factor_id": "cn_a.stable_alpha_dl",
    "factor_name": "StableAlpha",
    "market": "CN_A",
    "universe_ref": "universe://csi-all-pit/v1",
    "inputs": ["open", "high", "low", "close", "volume", "amount", "vwap"],
    "label": {
        "name": "future_21d_vwap_return",
        "price_field": "vwap",
        "horizon": 21,
        "style_neutralize": ["size", "volatility", "reversal", "liquidity"],
    },
    "architecture": "MLP",
    "style_neutralize": ["size", "volatility", "reversal", "liquidity"],
    "sample_weighting": "INVERSE_SIZE",
    "expected_direction": "POSITIVE",
}

_FILES = {
    "model.py": b"def build_model(hyperparams: dict):\n    return None\n",
    "train.py": b"def train(data, spec: dict):\n    return None\n",
    "infer.py": b"def infer(data, weights):\n    return None\n",
}


class _FakeData:
    def pit_frame(
        self, *, instrument_ids, fields, decision_time, field_prefix="market.eod."
    ):
        return {"rows": []}

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
        return {"rows": []}


def make_client(
    principal_provider: Callable[[str], ResearchPrincipal | None] | None = None,
) -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    repository = SqlAlchemyFactorConstructionRepository(engine)
    provider = principal_provider or (
        lambda token: ResearchPrincipal(
            actor_id="researcher-1",
            grants=frozenset(
                {
                    ResearchGrant(capability=cap, project_id="local", market="CN_A")
                    for cap in _CAPS
                }
            ),
        )
        if token == "test-researcher"
        else None
    )
    app = create_app(
        readiness_probe=lambda: {"postgres": True, "minio": True},
        research_repository=SqlAlchemyResearchRepository(engine),
        factor_construction_repository=repository,
        factor_build_service=FactorBuildService(
            repository,
            InMemoryArtifactStore(),
            _FakeData(),  # type: ignore[arg-type]
        ),
        research_principal_provider=provider,
    )
    return TestClient(app)


def _auth() -> dict[str, str]:
    return {
        "Authorization": "Bearer test-researcher",
        "Idempotency-Key": "test-idempotency-key-0001",
    }


def test_create_spec_requires_auth() -> None:
    client = make_client()
    response = client.post(
        "/v1/factor-build-specs",
        json={"metadata": _metadata(), "spec": _SPEC},
    )
    assert response.status_code == 401


def test_create_and_freeze_spec() -> None:
    client = make_client()
    created = client.post(
        "/v1/factor-build-specs",
        json={"metadata": _metadata(), "spec": _SPEC},
        headers=_auth(),
    )
    assert created.status_code == 202
    spec_id = created.json()["id"]
    assert created.json()["state"] == "DRAFT"

    frozen = client.post(
        f"/v1/factor-build-specs/{spec_id}:freeze",
        json={"metadata": _metadata()},
        headers={**_auth(), "If-Match": '"1"'},
    )
    assert frozen.status_code == 202
    assert frozen.json()["state"] == "FROZEN"


def test_freeze_requires_if_match() -> None:
    client = make_client()
    created = client.post(
        "/v1/factor-build-specs",
        json={"metadata": _metadata(), "spec": _SPEC},
        headers=_auth(),
    )
    spec_id = created.json()["id"]
    response = client.post(
        f"/v1/factor-build-specs/{spec_id}:freeze",
        json={"metadata": _metadata()},
        headers=_auth(),
    )
    assert response.status_code == 422


def test_generate_bundle_requires_frozen_spec() -> None:
    client = make_client()
    created = client.post(
        "/v1/factor-build-specs",
        json={"metadata": _metadata(), "spec": _SPEC},
        headers=_auth(),
    )
    body = created.json()
    spec_hash = body["spec_hash"]
    manifest = build_code_bundle(_FILES, spec_hash=spec_hash)
    response = client.post(
        f"/v1/factor-build-specs/{body['id']}:generate",
        json={
            "metadata": _metadata(),
            "spec_hash": spec_hash,
            "bundle_hash": bundle_hash(manifest),
            "manifest": manifest,
            "files": _files_text(),
        },
        headers=_auth(),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SPEC_NOT_FROZEN"


def test_generate_bundle_against_frozen_spec() -> None:
    client = make_client()
    created = client.post(
        "/v1/factor-build-specs",
        json={"metadata": _metadata(), "spec": _SPEC},
        headers=_auth(),
    )
    body = created.json()
    spec_id = body["id"]
    spec_hash = body["spec_hash"]
    client.post(
        f"/v1/factor-build-specs/{spec_id}:freeze",
        json={"metadata": _metadata()},
        headers={**_auth(), "If-Match": '"1"'},
    )
    manifest = build_code_bundle(_FILES, spec_hash=spec_hash)
    response = client.post(
        f"/v1/factor-build-specs/{spec_id}:generate",
        json={
            "metadata": _metadata(),
            "spec_hash": spec_hash,
            "bundle_hash": bundle_hash(manifest),
            "manifest": manifest,
            "files": _files_text(),
        },
        headers=_auth(),
    )
    assert response.status_code == 202
    assert response.json()["bundle_hash"].startswith("sha256:")


def _files_text() -> dict[str, str]:
    return {name: payload.decode() for name, payload in _FILES.items()}


def _metadata() -> dict[str, object]:
    return {
        "reason": "Build a StableAlpha factor from the report",
        "parent_artifact_id": None,
        "budget": {
            "candidate_limit": 1,
            "llm_token_limit": 1000,
            "cpu_hours": 1,
            "wall_clock_minutes": 30,
        },
        "schema_version": "1.0",
    }
