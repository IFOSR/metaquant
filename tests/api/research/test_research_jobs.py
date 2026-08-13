from collections.abc import Callable
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.api.app import create_app
from quant_platform.research.api import (
    ResearchGrant,
    ResearchPrincipal,
    adapt_security_principal_provider,
)
from quant_platform.research.models import Base
from quant_platform.research.repository import SqlAlchemyResearchRepository
from quant_platform.security import (
    AuthenticationMethod,
    Capability,
    Environment,
    Market,
    Principal,
    Scope,
    StaticBearerPrincipalProvider,
)


def make_client(
    principal_provider: Callable[[str], ResearchPrincipal | None] | None = None,
) -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    repository = SqlAlchemyResearchRepository(engine)
    provider = principal_provider or (
        lambda token: ResearchPrincipal(
            actor_id="researcher-1",
            grants=frozenset(
                {
                    ResearchGrant(
                        capability="research.jobs.manage",
                        project_id="local",
                        market="CN_A",
                    ),
                    ResearchGrant(
                        capability="research.jobs.manage",
                        project_id="local",
                        market="CN_COMMODITY_FUTURES",
                    ),
                }
            ),
        )
        if token == "test-researcher"
        else None
    )
    app = create_app(
        readiness_probe=lambda: {"postgres": True, "minio": True},
        research_repository=repository,
        research_principal_provider=provider,
    )
    return TestClient(app)


def metadata() -> dict[str, object]:
    return {
        "reason": "Create a preregistered research workspace",
        "parent_artifact_id": None,
        "budget": {
            "candidate_limit": 10,
            "llm_token_limit": 1000,
            "cpu_hours": 1,
            "wall_clock_minutes": 30,
        },
        "schema_version": "1.0",
    }


def brief() -> dict[str, object]:
    return {
        "hypothesis": "Inventory pressure predicts forward returns",
        "economic_mechanism": "Scarcity affects marginal pricing.",
        "expected_direction": "NEGATIVE",
        "falsification_conditions": ["No positive net OOS contribution"],
        "allowed_data_domains": ["formal.market.eod"],
        "forbidden_data_domains": ["future.revisions"],
        "constraints": ["daily only"],
        "evidence_ref_ids": [],
        "uncertainties": ["inventory publication lag"],
    }


def auth_headers(**extra: str) -> dict[str, str]:
    return {"Authorization": "Bearer test-researcher", **extra}


def test_create_job_is_authenticated_idempotent_and_returns_snapshot() -> None:
    client = make_client()
    command = {
        "metadata": metadata(),
        "market": "CN_A",
        "universe_ref": "universe://csi500/pit",
        "frequency": "1d",
        "decision_clock": "T_CLOSE",
        "trade_clock": "T_PLUS_1_OPEN",
        "horizon": "20TD",
        "research_brief_version_id": "brief://seed",
    }
    headers = auth_headers(**{"Idempotency-Key": "create-job-000001"})

    first = client.post("/v1/research-jobs", json=command, headers=headers)
    second = client.post("/v1/research-jobs", json=command, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json() == second.json()
    job_id = first.json()["resource_id"]

    snapshot = client.get(f"/v1/research-jobs/{job_id}", headers=auth_headers())
    assert snapshot.status_code == 200
    assert snapshot.headers["etag"] == '"1"'
    assert snapshot.json()["owner"] == "researcher-1"
    assert snapshot.json()["market"] == "CN_A"
    assert snapshot.json()["environment"] == "RESEARCH"

    listing = client.get("/v1/research-jobs", headers=auth_headers())
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [job_id]


def test_futures_job_requires_market_specific_fields() -> None:
    client = make_client()
    response = client.post(
        "/v1/research-jobs",
        json={
            "metadata": metadata(),
            "market": "CN_COMMODITY_FUTURES",
            "universe_ref": "universe://futures/initial",
            "frequency": "1d",
            "decision_clock": "SETTLEMENT",
            "trade_clock": "NEXT_SESSION_OPEN",
            "horizon": "20TD",
            "research_brief_version_id": "brief://seed",
        },
        headers=auth_headers(**{"Idempotency-Key": "create-job-000002"}),
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_brief_draft_update_and_freeze_use_strong_etags() -> None:
    client = make_client()
    job_receipt = client.post(
        "/v1/research-jobs",
        json={
            "metadata": metadata(),
            "market": "CN_A",
            "universe_ref": "universe://csi300/pit",
            "frequency": "1d",
            "decision_clock": "T_CLOSE",
            "trade_clock": "T_PLUS_1_OPEN",
            "horizon": "20TD",
            "research_brief_version_id": "brief://seed",
        },
        headers=auth_headers(**{"Idempotency-Key": "create-job-000003"}),
    )
    job_id = job_receipt.json()["resource_id"]

    created = client.post(
        f"/v1/research-jobs/{job_id}/brief-versions",
        json={"metadata": metadata(), "brief": brief()},
        headers=auth_headers(
            **{"Idempotency-Key": "create-brief-0001", "If-Match": '"1"'}
        ),
    )
    assert created.status_code == 202
    brief_id = created.json()["resource_id"]

    draft = client.get(
        f"/v1/research-brief-versions/{brief_id}",
        headers=auth_headers(),
    )
    assert draft.status_code == 200
    assert draft.headers["etag"] == '"1"'
    assert draft.json()["status"] == "DRAFT"

    updated_brief = brief()
    updated_brief["hypothesis"] = "Revised inventory hypothesis"
    updated = client.patch(
        f"/v1/research-brief-versions/{brief_id}",
        json={"metadata": metadata(), "brief": updated_brief},
        headers=auth_headers(
            **{"Idempotency-Key": "update-brief-0001", "If-Match": '"1"'}
        ),
    )
    assert updated.status_code == 202

    frozen = client.post(
        f"/v1/research-brief-versions/{brief_id}:freeze",
        json=metadata(),
        headers=auth_headers(
            **{"Idempotency-Key": "freeze-brief-0001", "If-Match": '"2"'}
        ),
    )
    assert frozen.status_code == 202

    snapshot = client.get(
        f"/v1/research-brief-versions/{brief_id}",
        headers=auth_headers(),
    )
    assert snapshot.headers["etag"] == '"3"'
    assert snapshot.json()["status"] == "FROZEN"
    assert snapshot.json()["content_hash"].startswith("sha256:")

    rejected = client.patch(
        f"/v1/research-brief-versions/{brief_id}",
        json={"metadata": metadata(), "brief": brief()},
        headers=auth_headers(
            **{"Idempotency-Key": "update-brief-0002", "If-Match": '"3"'}
        ),
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "BRIEF_NOT_DRAFT"


def test_undisclosed_job_uses_same_safe_404_as_missing_job() -> None:
    client = make_client(
        lambda token: ResearchPrincipal(
            actor_id="a-share-only",
            grants=frozenset(
                {
                    ResearchGrant(
                        capability="research.jobs.read",
                        project_id="local",
                        market="CN_A",
                    )
                }
            ),
        )
        if token == "limited"
        else ResearchPrincipal(
            actor_id="futures-owner",
            grants=frozenset(
                {
                    ResearchGrant(
                        capability="research.jobs.manage",
                        project_id="local",
                        market="CN_COMMODITY_FUTURES",
                    )
                }
            ),
        )
        if token == "owner"
        else None
    )
    command = {
        "metadata": metadata(),
        "market": "CN_COMMODITY_FUTURES",
        "universe_ref": "universe://futures/initial",
        "frequency": "1d",
        "decision_clock": "SETTLEMENT",
        "trade_clock": "NEXT_SESSION_OPEN",
        "settlement_clock": "DAILY_SETTLEMENT",
        "exchange_scope": ["SHFE"],
        "contract_selection": "ACTUAL_CONTRACTS_ONLY",
        "roll_policy": "roll://rb/volume-no-future/v1",
        "horizon": "20TD",
        "research_brief_version_id": "brief://seed",
    }
    created = client.post(
        "/v1/research-jobs",
        json=command,
        headers={
            "Authorization": "Bearer owner",
            "Idempotency-Key": "create-job-000004",
        },
    )
    job_id = created.json()["resource_id"]

    hidden = client.get(
        f"/v1/research-jobs/{job_id}",
        headers={"Authorization": "Bearer limited"},
    )
    missing = client.get(
        "/v1/research-jobs/rj_missing",
        headers={"Authorization": "Bearer limited"},
    )

    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["code"] == missing.json()["code"] == "RESOURCE_NOT_FOUND"


def test_read_only_and_other_project_principals_cannot_mutate_local_jobs() -> None:
    grants = {
        "owner": frozenset(
            {
                ResearchGrant(
                    capability="research.jobs.manage",
                    project_id="local",
                    market="CN_A",
                )
            }
        ),
        "reader": frozenset(
            {
                ResearchGrant(
                    capability="research.jobs.read",
                    project_id="local",
                    market="CN_A",
                )
            }
        ),
        "other-project": frozenset(
            {
                ResearchGrant(
                    capability="research.jobs.manage",
                    project_id="project-beta",
                    market="CN_A",
                )
            }
        ),
    }
    client = make_client(
        lambda token: ResearchPrincipal(actor_id=token, grants=grants[token])
        if token in grants
        else None
    )
    command = {
        "metadata": metadata(),
        "market": "CN_A",
        "universe_ref": "universe://csi500/pit",
        "frequency": "1d",
        "decision_clock": "T_CLOSE",
        "trade_clock": "T_PLUS_1_OPEN",
        "horizon": "20TD",
        "research_brief_version_id": "brief://seed",
    }
    created = client.post(
        "/v1/research-jobs",
        json=command,
        headers={
            "Authorization": "Bearer owner",
            "Idempotency-Key": "create-job-authz-001",
        },
    )
    job_id = created.json()["resource_id"]

    assert (
        client.get(
            f"/v1/research-jobs/{job_id}",
            headers={"Authorization": "Bearer reader"},
        ).status_code
        == 200
    )
    denied_create = client.post(
        "/v1/research-jobs",
        json=command,
        headers={
            "Authorization": "Bearer reader",
            "Idempotency-Key": "create-job-authz-002",
        },
    )
    denied_brief = client.post(
        f"/v1/research-jobs/{job_id}/brief-versions",
        json={"metadata": metadata(), "brief": brief()},
        headers={
            "Authorization": "Bearer reader",
            "Idempotency-Key": "create-brief-authz-01",
            "If-Match": '"1"',
        },
    )
    hidden = client.get(
        f"/v1/research-jobs/{job_id}",
        headers={"Authorization": "Bearer other-project"},
    )

    assert denied_create.status_code == 404
    assert denied_brief.status_code == 404
    assert hidden.status_code == 404


def test_security_adapter_preserves_exact_capability_and_project_scope() -> None:
    principal = Principal(
        subject="reader-1",
        display_name="Read Only",
        authentication_method=AuthenticationMethod.TEST_BEARER,
        authenticated_at=datetime(2026, 8, 12, tzinfo=UTC),
        capabilities=frozenset(
            {
                Capability(
                    name="research.jobs.read",
                    scope=Scope(
                        project_id="project-beta",
                        market=Market.CN_A,
                        environment=Environment.RESEARCH,
                    ),
                )
            }
        ),
    )
    provider = StaticBearerPrincipalProvider({"reader": principal})
    resolved = adapt_security_principal_provider(provider)("reader")

    assert resolved is not None
    assert resolved.scopes({"research.jobs.read"}) == frozenset(
        {("project-beta", "CN_A")}
    )
    assert resolved.scopes({"research.jobs.manage"}) == frozenset()
