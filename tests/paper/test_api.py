"""API tests for paper account lifecycle."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.artifacts.store import InMemoryArtifactStore
from quant_platform.paper.api import build_paper_router
from quant_platform.paper.artifact import StrategyArtifactStore
from quant_platform.paper.repository import SqlAlchemyPaperRepository
from quant_platform.research.api import (
    ResearchGrant,
    ResearchPrincipal,
    install_problem_handlers,
)
from quant_platform.research.models import Base
from quant_platform.strategy_generation.repository import (
    SqlAlchemyStrategyRepository,
)
from quant_platform.strategy_generation.schemas import AgentOutput

_HEADERS = {"Authorization": "Bearer paper-tester"}
_SAFE_CODE = (
    "from nautilus_trader.trading.strategy import Strategy\n"
    "class GenStrategy(Strategy):\n"
    "    pass\n"
)


def _provider(token: str) -> ResearchPrincipal | None:
    if token != "paper-tester":
        return None
    grants = frozenset(
        ResearchGrant(name, "local", market)
        for market in ("CN_A", "CN_COMMODITY_FUTURES")
        for name in ("paper.read", "paper.write")
    )
    return ResearchPrincipal(actor_id="paper-tester-1", grants=grants)


def _make_client() -> tuple[TestClient, SqlAlchemyStrategyRepository]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    drafts = SqlAlchemyStrategyRepository(engine)
    application = FastAPI()
    install_problem_handlers(application)
    application.include_router(
        build_paper_router(
            SqlAlchemyPaperRepository(engine),
            _provider,
            drafts,
            StrategyArtifactStore(InMemoryArtifactStore()),
        )
    )
    return TestClient(application), drafts


def _frozen_draft(drafts: SqlAlchemyStrategyRepository) -> str:
    draft = drafts.create_draft(actor_id="paper-tester-1", market="CN_A")
    drafts.apply_turn(
        draft_id=draft.id,
        user_content="make a strategy",
        output=AgentOutput(
            title="MA cross",
            explanation="Buy on cross.",
            question="",
            code=_SAFE_CODE,
            ready=True,
            instrument_ids=["600000.SH"],
            frequency="1d",
        ),
    )
    return drafts.freeze(draft_id=draft.id, actor_id="paper-tester-1").id


def test_missing_authorization_returns_401() -> None:
    client, _drafts = _make_client()
    response = client.post("/v1/paper/accounts", json={"draft_id": "sd_x"})
    assert response.status_code == 401


def test_create_requires_frozen_draft() -> None:
    client, drafts = _make_client()
    draft = drafts.create_draft(actor_id="paper-tester-1", market="CN_A")
    response = client.post(
        "/v1/paper/accounts",
        json={"draft_id": draft.id},
        headers=_HEADERS,
    )
    assert response.status_code == 409


def test_create_and_full_lifecycle() -> None:
    client, drafts = _make_client()
    draft_id = _frozen_draft(drafts)

    created = client.post(
        "/v1/paper/accounts",
        json={"draft_id": draft_id, "initial_cash": "500000"},
        headers=_HEADERS,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["state"] == "ACTIVE"
    assert body["initial_cash"] == 500000.0
    assert body["artifact_address"]
    account_id = body["id"]

    paused = client.post(f"/v1/paper/accounts/{account_id}:pause", headers=_HEADERS)
    assert paused.json()["state"] == "PAUSED"
    resumed = client.post(f"/v1/paper/accounts/{account_id}:resume", headers=_HEADERS)
    assert resumed.json()["state"] == "ACTIVE"
    closed = client.post(f"/v1/paper/accounts/{account_id}:close", headers=_HEADERS)
    assert closed.json()["state"] == "CLOSED"

    again = client.post(f"/v1/paper/accounts/{account_id}:resume", headers=_HEADERS)
    assert again.status_code == 409

    listed = client.get("/v1/paper/accounts", headers=_HEADERS)
    assert [item["id"] for item in listed.json()["accounts"]] == [account_id]


def test_ledger_endpoints_empty() -> None:
    client, drafts = _make_client()
    draft_id = _frozen_draft(drafts)
    account_id = client.post(
        "/v1/paper/accounts", json={"draft_id": draft_id}, headers=_HEADERS
    ).json()["id"]
    for path in ("orders", "fills", "positions", "equity"):
        response = client.get(
            f"/v1/paper/accounts/{account_id}/{path}", headers=_HEADERS
        )
        assert response.status_code == 200
        assert list(response.json().values())[0] == []


def test_unknown_account_404() -> None:
    client, _drafts = _make_client()
    response = client.get("/v1/paper/accounts/pa_nope", headers=_HEADERS)
    assert response.status_code == 404
