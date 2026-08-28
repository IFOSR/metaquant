"""API tests for natural-language strategy drafting (fake runner)."""

from __future__ import annotations

import json
from collections.abc import Callable
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.research.api import (
    ResearchGrant,
    ResearchPrincipal,
    install_problem_handlers,
)
from quant_platform.research.models import Base
from quant_platform.strategy_generation.api import build_strategy_router
from quant_platform.strategy_generation.repository import (
    SqlAlchemyStrategyRepository,
)

_HEADERS = {"Authorization": "Bearer strategy-tester"}

_READY = {
    "title": "MA cross",
    "explanation": "Buy when the 5-day MA crosses above the 20-day MA.",
    "question": "",
    "code": "class MAStrategy(Strategy): ...",
    "ready": True,
    "instrument_ids": ["600000.SH"],
    "frequency": "1d",
}


def _provider(token: str) -> ResearchPrincipal | None:
    if token != "strategy-tester":
        return None
    grants = frozenset(
        ResearchGrant(name, "local", market)
        for market in ("CN_A", "CN_COMMODITY_FUTURES")
        for name in ("strategy.write", "strategy.read")
    )
    return ResearchPrincipal(actor_id="strategy-tester-1", grants=grants)


def _make_client(
    runner: Callable[[str], str],
    backtest_service: object | None = None,
    execution_state: object | None = None,
) -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    repository = SqlAlchemyStrategyRepository(engine)
    application = FastAPI()
    install_problem_handlers(application)
    application.include_router(
        build_strategy_router(
            repository,
            _provider,
            runner,
            backtest_service,  # type: ignore[arg-type]
            execution_state,  # type: ignore[arg-type]
        )
    )
    return TestClient(application)


def _ok(_prompt: str) -> str:
    return json.dumps(_READY)


def test_create_draft_runs_first_turn() -> None:
    client = _make_client(_ok)
    response = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉买入，死叉卖出"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["market"] == "CN_A"
    assert body["ready"] is True
    assert body["code"] is not None
    assert body["state"] == "READY"


def test_draft_snapshot_exposes_research_lifecycle() -> None:
    """统一研究容器：快照带 kind + stage + 生命周期证据字段。"""
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    assert created["kind"] == "strategy"
    assert created["stage"] == "READY"
    assert created["code_test_result"] is None
    assert created["backtest_results"] == []
    assert created["paper_binding"] is None


def test_backtest_appends_traceable_history() -> None:
    service = Mock()
    service.run.return_value = {
        "schema_version": "strategy-backtest/v1",
        "backtest_hash": "hash-1",
        "start": "2025-01-01",
        "end": "2026-01-01",
        "frequency": "1d",
        "metrics": {"total_return": 0.1},
        "equity_curve": [],
        "error": None,
    }
    client = _make_client(_ok, backtest_service=service)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}:backtest",
        headers=_HEADERS,
    )
    assert response.status_code == 200, response.text
    got = client.get(f"/v1/strategy-drafts/{created['id']}", headers=_HEADERS).json()
    assert len(got["backtest_results"]) == 1
    assert got["backtest_results"][0]["backtest_hash"] == "hash-1"
    assert got["stage"] == "BACKTESTED"


def test_post_message_appends_turn() -> None:
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}/messages",
        headers=_HEADERS,
        json={"message": "加上 5% 止损"},
    )
    assert response.status_code == 202, response.text

    got = client.get(f"/v1/strategy-drafts/{created['id']}", headers=_HEADERS)
    assert got.status_code == 200
    assert [message["role"] for message in got.json()["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_freeze_ready_draft() -> None:
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}:freeze",
        headers=_HEADERS,
    )
    assert response.status_code == 202, response.text
    assert response.json()["state"] == "FROZEN"


def test_message_on_frozen_draft_returns_409() -> None:
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    frozen = client.post(
        f"/v1/strategy-drafts/{created['id']}:freeze",
        headers=_HEADERS,
    )
    assert frozen.status_code == 202
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}/messages",
        headers=_HEADERS,
        json={"message": "改成只做多"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "STRATEGY_DRAFT_FROZEN"
    # 冻结态不可被对话改写：状态与 resource_version 保持不变
    got = client.get(f"/v1/strategy-drafts/{created['id']}", headers=_HEADERS)
    assert got.json()["state"] == "FROZEN"
    assert got.json()["resource_version"] == 3


def test_list_strategy_drafts_returns_frozen() -> None:
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    client.post(
        f"/v1/strategy-drafts/{created['id']}:freeze",
        headers=_HEADERS,
    )
    response = client.get("/v1/strategy-drafts?state=FROZEN", headers=_HEADERS)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert any(item["id"] == created["id"] for item in items)
    assert all(item["state"] == "FROZEN" for item in items)
    saved = next(item for item in items if item["id"] == created["id"])
    assert saved["content_hash"] is not None
    assert saved["market"] == "CN_A"


def test_list_strategy_drafts_excludes_unfrozen() -> None:
    client = _make_client(_ok)
    client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    )
    response = client.get("/v1/strategy-drafts?state=FROZEN", headers=_HEADERS)
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_unfreeze_returns_ready() -> None:
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    client.post(
        f"/v1/strategy-drafts/{created['id']}:freeze",
        headers=_HEADERS,
    )
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}:unfreeze",
        headers=_HEADERS,
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["state"] == "READY"
    assert body["content_hash"] is None
    assert body["ready"] is True


def test_unfreeze_requires_frozen_returns_409() -> None:
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}:unfreeze",
        headers=_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "STRATEGY_DRAFT_NOT_FROZEN"


def test_freeze_not_ready_returns_409() -> None:
    def not_ready(_prompt: str) -> str:
        payload = {**_READY, "ready": False, "code": None, "question": "止损多少?"}
        return json.dumps(payload)

    client = _make_client(not_ready)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}:freeze",
        headers=_HEADERS,
    )
    assert response.status_code == 409


def test_missing_authorization_returns_401() -> None:
    client = _make_client(_ok)
    response = client.post(
        "/v1/strategy-drafts",
        json={"market": "CN_A", "first_message": "均线金叉"},
    )
    assert response.status_code == 401


def test_problem_error_str_is_readable() -> None:
    """str(ProblemError) 必须可读：backtest 兜底 payload 的 error 字段依赖它。"""
    from quant_platform.research.api import ProblemError

    exc = ProblemError(
        status=422,
        code="INVALID_FREQUENCY",
        title="Invalid frequency",
        detail="frequency must be one of 1d, 1w, 5m, 15m, 30m, 60m.",
    )
    assert str(exc) == "frequency must be one of 1d, 1w, 5m, 15m, 30m, 60m."


def test_backtest_ready_draft_returns_result() -> None:
    service = Mock()
    service.run.return_value = {
        "metrics": {"total_return": 0.1},
        "equity_curve": [{"date": "2026-08-01", "equity": 1100000.0}],
        "error": None,
    }
    client = _make_client(_ok, backtest_service=service)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}:backtest",
        headers=_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["total_return"] == 0.1


def test_backtest_not_ready_returns_409() -> None:
    def not_ready(_prompt: str) -> str:
        payload = {**_READY, "ready": False, "code": None, "question": "止损多少?"}
        return json.dumps(payload)

    client = _make_client(not_ready, backtest_service=Mock())
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}:backtest",
        headers=_HEADERS,
    )
    assert response.status_code == 409


def test_backtest_invalid_frequency_returns_422() -> None:
    """非法周期是客户端错误：必须 422 Problem，不能被兜底吞成假成功。"""
    service = Mock()
    client = _make_client(_ok, backtest_service=service)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}:backtest?frequency=2d",
        headers=_HEADERS,
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "INVALID_FREQUENCY"
    service.run.assert_not_called()


def test_paper_records_open_positions() -> None:
    position = {
        "instrument_id": "600000.SSE",
        "entry": "BUY",
        "peak_qty": 100.0,
        "avg_px_open": 10.0,
        "avg_px_close": None,
        "realized_pnl": 0.0,
        "opened_at": "2026-08-01",
        "closed_at": None,
    }
    service = Mock()
    service.run.return_value = {
        "metrics": {"total_return": 0.1},
        "equity_curve": [],
        "positions": [position],
        "error": None,
    }
    execution_state = Mock()
    client = _make_client(
        _ok, backtest_service=service, execution_state=execution_state
    )
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}:paper",
        headers=_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["paper_positions"]["600000.SSE"]["entry"] == "BUY"
    execution_state.record_paper_positions.assert_called_once()


def test_upload_attachment_extracts_text() -> None:
    client = _make_client(_ok)
    response = client.post(
        "/v1/strategy-drafts/attachments?market=CN_A",
        headers=_HEADERS,
        files={"file": ("report.txt", b"buy on ma cross", "text/plain")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "report.txt"
    assert body["kind"] == "text"
    assert body["extracted_text"] == "buy on ma cross"


def test_upload_attachment_image_returns_reference() -> None:
    client = _make_client(_ok)
    response = client.post(
        "/v1/strategy-drafts/attachments?market=CN_A",
        headers=_HEADERS,
        files={
            "file": (
                "chart.png",
                b"\x89PNG\r\n\x1a\n" + b"x" * 16,
                "image/png",
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "image"
    assert body["extracted_text"] == ""
