"""Tests for the drift comparison and its API endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.artifacts.store import InMemoryArtifactStore
from quant_platform.paper.api import build_paper_router
from quant_platform.paper.artifact import StrategyArtifactStore
from quant_platform.paper.drift import compute_drift
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
        for market in ("CN_A",)
        for name in ("paper.read", "paper.write")
    )
    return ResearchPrincipal(actor_id="paper-tester-1", grants=grants)


def test_compute_drift_common_dates_and_max_diff() -> None:
    payload = {
        "equity_curve": [
            {"date": "2026-08-20", "equity": 1_000_000.0},
            {"date": "2026-08-21", "equity": 1_001_000.0},
            {"date": "2026-08-22", "equity": 1_002_000.0},
        ],
        "cost_basis": "net_of_fees",
        "backtest_hash": "abc",
    }
    paper_rows = [
        {"trade_date": "2026-08-21", "equity": 1_000_900.0},
        {"trade_date": "2026-08-22", "equity": 1_002_100.0},
    ]
    report = compute_drift(backtest_payload=payload, paper_equity=paper_rows)
    assert report["common_days"] == 2
    assert report["max_abs_diff"] == 100.0
    assert report["points"][0] == {
        "date": "2026-08-21",
        "backtest_equity": 1_001_000.0,
        "paper_equity": 1_000_900.0,
        "diff": -100.0,
    }


def test_compute_drift_no_overlap() -> None:
    report = compute_drift(
        backtest_payload={"equity_curve": [{"date": "2026-01-01", "equity": 1.0}]},
        paper_equity=[{"trade_date": "2026-02-01", "equity": 2.0}],
    )
    assert report["common_days"] == 0
    assert report["max_abs_diff"] == 0.0


def _make_client(
    backtest_service: object | None,
) -> tuple[TestClient, SqlAlchemyStrategyRepository, SqlAlchemyPaperRepository]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    drafts = SqlAlchemyStrategyRepository(engine)
    repository = SqlAlchemyPaperRepository(engine)
    application = FastAPI()
    install_problem_handlers(application)
    application.include_router(
        build_paper_router(
            repository,
            _provider,
            drafts,
            StrategyArtifactStore(InMemoryArtifactStore()),
            backtest_service,
        )
    )
    return TestClient(application), drafts, repository


def _create_account(client: TestClient, drafts: SqlAlchemyStrategyRepository) -> str:
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
    draft_id = drafts.freeze(draft_id=draft.id, actor_id="paper-tester-1").id
    return str(
        client.post(
            "/v1/paper/accounts", json={"draft_id": draft_id}, headers=_HEADERS
        ).json()["id"]
    )


def test_drift_endpoint_unavailable_without_service_takes_priority() -> None:
    """服务未配置（503）优先于账本为空（409）。"""
    client, drafts, _repository = _make_client(None)
    account_id = _create_account(client, drafts)
    response = client.get(f"/v1/paper/accounts/{account_id}/drift", headers=_HEADERS)
    assert response.status_code == 503


def test_drift_endpoint_computes_report() -> None:
    class FakeBacktestService:
        def run(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["market"] == "CN_A"
            assert kwargs["frequency"] == "1d"
            assert Decimal("1000000") == kwargs["initial_cash"]
            return {
                "equity_curve": [
                    {"date": "2026-08-21", "equity": 1_000_000.0},
                ],
                "cost_basis": "net_of_fees",
                "backtest_hash": "abc123",
            }

    client, drafts, repository = _make_client(FakeBacktestService())
    account_id = _create_account(client, drafts)
    repository.record_equity(
        account_id=account_id,
        trade_date="2026-08-21",
        equity=Decimal("999800"),
        cash=Decimal("900000"),
    )
    response = client.get(f"/v1/paper/accounts/{account_id}/drift", headers=_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["common_days"] == 1
    assert body["points"][0]["diff"] == -200.0
    assert body["backtest_hash"] == "abc123"


def test_drift_endpoint_reports_backtest_failure() -> None:
    class FailingService:
        def run(self, **kwargs: object) -> dict[str, object]:
            return {"error": "MARKET_DATA_NOT_INGESTED"}

    client, drafts, repository = _make_client(FailingService())
    account_id = _create_account(client, drafts)
    repository.record_equity(
        account_id=account_id,
        trade_date=datetime.now(UTC).date().isoformat(),
        equity=Decimal("1000000"),
        cash=Decimal("1000000"),
    )
    response = client.get(f"/v1/paper/accounts/{account_id}/drift", headers=_HEADERS)
    assert response.status_code == 502


def test_drift_endpoint_unavailable_without_service() -> None:
    client, drafts, repository = _make_client(None)
    account_id = _create_account(client, drafts)
    repository.record_equity(
        account_id=account_id,
        trade_date=datetime.now(UTC).date().isoformat(),
        equity=Decimal("1000000"),
        cash=Decimal("1000000"),
    )
    response = client.get(f"/v1/paper/accounts/{account_id}/drift", headers=_HEADERS)
    assert response.status_code == 503
