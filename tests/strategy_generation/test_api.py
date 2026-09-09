"""API tests for natural-language strategy drafting (fake runner)."""

from __future__ import annotations

import json
from collections.abc import Callable
from unittest.mock import Mock

import pytest
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
    "code": (
        "INDICATORS = []\n"
        "def compute_signal(ctx):\n"
        "    return Signal(target_qty=1)\n"
    ),
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
    # 代码快照仅供服务端重放，不随草稿快照下发（避免载荷膨胀）
    assert "code" not in got["backtest_results"][0]
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


def test_post_message_stream_emits_events() -> None:
    """流式消息端点：SSE 返回阶段事件 + 最终草稿。"""
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.post(
        f"/v1/strategy-drafts/{created['id']}/messages/stream",
        headers=_HEADERS,
        json={"message": "加个止损"},
    )
    assert response.status_code == 200, response.text
    assert "text/event-stream" in response.headers["content-type"]
    body = response.text
    assert "event: stage" in body
    assert "event: draft" in body
    assert created["id"] in body  # 最终草稿快照里包含草稿 id


def test_update_parameters_preserves_code() -> None:
    """确定性参数更新：改标的/周期/区间，策略代码一字不动。"""
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.patch(
        f"/v1/strategy-drafts/{created['id']}",
        headers=_HEADERS,
        json={
            "instrument_ids": ["600519.SH"],
            "frequency": "1w",
            "start": "2021-09-08",
            "end": "2026-09-08",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["instrument_ids"] == ["600519.SH"]
    assert body["frequency"] == "1w"
    assert body["code"] == created["code"]  # 代码不动
    assert body["backtest_plan"]["start"] == "2021-09-08"


def test_update_parameters_rejects_market_instrument_mismatch() -> None:
    """参数更新必须保持市场/标的匹配（A 股不能塞期货标的）。"""
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.patch(
        f"/v1/strategy-drafts/{created['id']}",
        headers=_HEADERS,
        json={"instrument_ids": ["P8888.DCE"]},
    )
    assert response.status_code == 422, response.text


def test_delete_strategy_draft() -> None:
    client = _make_client(_ok)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    response = client.delete(
        f"/v1/strategy-drafts/{created['id']}",
        headers=_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] == created["id"]
    got = client.get(f"/v1/strategy-drafts/{created['id']}", headers=_HEADERS)
    assert got.status_code == 404


def test_clear_strategy_drafts() -> None:
    client = _make_client(_ok)
    for _ in range(3):
        client.post(
            "/v1/strategy-drafts",
            headers=_HEADERS,
            json={"market": "CN_A", "first_message": "均线金叉"},
        )
    listed = client.get("/v1/strategy-drafts", headers=_HEADERS).json()
    assert len(listed["items"]) == 3
    response = client.delete("/v1/strategy-drafts", headers=_HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] == 3
    listed = client.get("/v1/strategy-drafts", headers=_HEADERS).json()
    assert listed["items"] == []


def test_backtest_context_contract() -> None:
    service = Mock()
    service.run.return_value = {
        "schema_version": "strategy-backtest/v1",
        "backtest_hash": "hash-context-1",
        "start": "2026-03-07",
        "end": "2026-09-07",
        "frequency": "15m",
        "metrics": {
            "total_return": 0.12,
            "sharpe": 1.2,
            "max_drawdown": 0.04,
            "trade_count": 2,
        },
        "equity_curve": [],
        "trades": [],
        "positions": [],
        "error": None,
    }
    client = _make_client(_ok, backtest_service=service)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    client.post(
        f"/v1/strategy-drafts/{created['id']}:backtest",
        headers=_HEADERS,
    )

    response = client.post(
        f"/v1/strategy-drafts/{created['id']}/messages",
        headers=_HEADERS,
        json={
            "message": "分析这次回测并提出优化建议",
            "backtest_hash": "hash-context-1",
        },
    )

    assert response.status_code == 202, response.text
    messages = client.get(
        f"/v1/strategy-drafts/{created['id']}",
        headers=_HEADERS,
    ).json()["messages"]
    assert messages[-2]["attachments"][0]["kind"] == "backtest"
    assert messages[-2]["attachments"][0]["backtest_hash"] == "hash-context-1"


def test_imported_backtest_is_injected_into_agent_context() -> None:
    prompts: list[str] = []

    def runner(prompt: str) -> str:
        prompts.append(prompt)
        return _ok(prompt)

    service = Mock()
    service.run.return_value = {
        "schema_version": "strategy-backtest/v1",
        "backtest_hash": "hash-context-2",
        "start": "2026-03-07",
        "end": "2026-09-07",
        "frequency": "15m",
        "metrics": {
            "total_return": -0.023,
            "sharpe": -0.4,
            "max_drawdown": 0.08,
            "trade_count": 4,
        },
        "total_fees": 128.0,
        "equity_curve": [],
        "trades": [
            {
                "time": "2026-05-07T05:45:00+00:00",
                "instrument_id": "SA8888.CZCE",
                "side": "BUY",
                "quantity": 1,
                "price": 1264,
                "action": "开多",
            }
        ],
        "positions": [],
        "venue_spec": {
            "market": "CN_COMMODITY_FUTURES",
            "cost_basis": "net_of_fees",
        },
        "error": None,
    }
    client = _make_client(runner, backtest_service=service)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    client.post(
        f"/v1/strategy-drafts/{created['id']}:backtest",
        headers=_HEADERS,
    )

    response = client.post(
        f"/v1/strategy-drafts/{created['id']}/messages",
        headers=_HEADERS,
        json={
            "message": "请分析这次回测为什么亏损",
            "backtest_hash": "hash-context-2",
        },
    )

    assert response.status_code == 202, response.text
    assert "请分析这次回测为什么亏损" in prompts[-1]
    assert "[导入的历史回测结果]" in prompts[-1]
    assert "总收益：-2.30%" in prompts[-1]
    assert "开多" in prompts[-1]
    assert service.run.call_count == 2


def test_replay_uses_code_snapshot_from_recording_time() -> None:
    """重放历史回测必须用录制时的代码快照，而不是草稿当前（可能已改版）的代码。"""
    code_v2 = (
        "INDICATORS = []\n"
        "def compute_signal(ctx):\n"
        "    return Signal(target_qty=1)\n"
    )

    def runner(prompt: str) -> str:
        if "反转" in prompt:
            return json.dumps({**_READY, "code": code_v2})
        return _ok(prompt)

    service = Mock()
    service.run.return_value = {
        "schema_version": "strategy-backtest/v1",
        "backtest_hash": "hash-v1",
        "start": "2025-01-01",
        "end": "2026-01-01",
        "frequency": "1d",
        "metrics": {"total_return": 0.1},
        "equity_curve": [],
        "error": None,
    }
    client = _make_client(runner, backtest_service=service)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    client.post(
        f"/v1/strategy-drafts/{created['id']}:backtest",
        headers=_HEADERS,
    )
    # 代码改版：agent 本轮返回 v2 代码
    client.post(
        f"/v1/strategy-drafts/{created['id']}/messages",
        headers=_HEADERS,
        json={"message": "改成反转策略"},
    )
    assert service.run.call_count == 1

    replayed = client.get(
        f"/v1/strategy-drafts/{created['id']}/backtests/hash-v1",
        headers=_HEADERS,
    )

    assert replayed.status_code == 200, replayed.text
    assert service.run.call_count == 2
    assert service.run.call_args.kwargs["code"] == _READY["code"]


def test_imported_backtest_survives_null_code_agent_turn() -> None:
    """agent 纯讨论轮返回 code=null 后，导入历史回测求建议必须仍然可用。"""
    discussion = {
        **_READY,
        "code": None,
        "ready": False,
        "instrument_ids": [],
        "question": "想聊聊哪部分思路？",
    }

    def runner(prompt: str) -> str:
        if "聊聊" in prompt:
            return json.dumps(discussion)
        return _ok(prompt)

    service = Mock()
    service.run.return_value = {
        "schema_version": "strategy-backtest/v1",
        "backtest_hash": "hash-null-code",
        "start": "2025-01-01",
        "end": "2026-01-01",
        "frequency": "1d",
        "metrics": {"total_return": 0.1},
        "equity_curve": [],
        "error": None,
    }
    client = _make_client(runner, backtest_service=service)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    client.post(
        f"/v1/strategy-drafts/{created['id']}:backtest",
        headers=_HEADERS,
    )
    # 纯讨论轮：agent 返回 code=null，不得影响后续回测导入
    client.post(
        f"/v1/strategy-drafts/{created['id']}/messages",
        headers=_HEADERS,
        json={"message": "我们聊聊思路"},
    )

    response = client.post(
        f"/v1/strategy-drafts/{created['id']}/messages",
        headers=_HEADERS,
        json={
            "message": "针对这次回测给些优化建议",
            "backtest_hash": "hash-null-code",
        },
    )

    assert response.status_code == 202, response.text
    assert service.run.call_count == 2


def test_unknown_backtest_hash_is_rejected_before_agent_call() -> None:
    runner = Mock(side_effect=lambda _prompt: _ok(""))
    service = Mock()
    service.run.return_value = {
        "backtest_hash": "hash-context-3",
        "start": "2026-03-07",
        "end": "2026-09-07",
        "frequency": "1d",
        "metrics": {},
        "equity_curve": [],
        "trades": [],
        "positions": [],
        "error": None,
    }
    client = _make_client(runner, backtest_service=service)
    created = client.post(
        "/v1/strategy-drafts",
        headers=_HEADERS,
        json={"market": "CN_A", "first_message": "均线金叉"},
    ).json()
    client.post(
        f"/v1/strategy-drafts/{created['id']}:backtest",
        headers=_HEADERS,
    )
    runner.reset_mock()

    response = client.post(
        f"/v1/strategy-drafts/{created['id']}/messages",
        headers=_HEADERS,
        json={
            "message": "分析回测",
            "backtest_hash": "not-owned-by-draft",
        },
    )

    assert response.status_code == 404, response.text
    runner.assert_not_called()
    assert service.run.call_count == 1


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


def test_upload_attachment_image_returns_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The API test should not depend on optional vision-provider credentials.
    from quant_platform.strategy_generation import api as strategy_api

    monkeypatch.setattr(
        strategy_api,
        "extract_attachment",
        lambda _name, _content: ("image", ""),
    )
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
