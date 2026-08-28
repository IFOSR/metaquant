"""Tests for strategy draft persistence and freeze discipline."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.research.models import Base
from quant_platform.strategy_generation.repository import (
    SqlAlchemyStrategyRepository,
)
from quant_platform.strategy_generation.schemas import (
    AgentOutput,
    StrategyDraftState,
)


def make_repository() -> SqlAlchemyStrategyRepository:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return SqlAlchemyStrategyRepository(engine)


def _output(*, ready: bool) -> AgentOutput:
    return AgentOutput(
        title="MA cross",
        explanation="Buy when the 5-day MA crosses above the 20-day MA.",
        question="What stop loss do you want?" if not ready else "",
        code="class MAStrategy(Strategy): ..." if ready else None,
        ready=ready,
        instrument_ids=["600000.SH"] if ready else [],
    )


def test_create_and_apply_turn() -> None:
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    assert draft.state is StrategyDraftState.DRAFT

    updated = repo.apply_turn(
        draft_id=draft.id,
        user_content="均线金叉买入",
        output=_output(ready=False),
    )
    assert updated.explanation == _output(ready=False).explanation
    assert updated.resource_version == 2

    messages = repo.list_messages(draft.id)
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].ordinal == 0
    assert messages[1].ordinal == 1


def test_apply_turn_marks_ready() -> None:
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    updated = repo.apply_turn(
        draft_id=draft.id,
        user_content="均线金叉买入",
        output=_output(ready=True),
    )
    assert updated.ready is True
    assert updated.state is StrategyDraftState.READY


def test_freeze_requires_ready() -> None:
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    repo.apply_turn(
        draft_id=draft.id,
        user_content="均线金叉买入",
        output=_output(ready=False),
    )
    with pytest.raises(ValueError):
        repo.freeze(draft_id=draft.id, actor_id="researcher-1")


def test_freeze_records_content_hash() -> None:
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    repo.apply_turn(
        draft_id=draft.id,
        user_content="均线金叉买入",
        output=_output(ready=True),
    )
    frozen = repo.freeze(draft_id=draft.id, actor_id="researcher-1")
    assert frozen.state is StrategyDraftState.FROZEN
    assert frozen.content_hash is not None
    assert len(frozen.content_hash) == 64


def test_apply_turn_rejects_frozen_draft() -> None:
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    repo.apply_turn(
        draft_id=draft.id,
        user_content="均线金叉买入",
        output=_output(ready=True),
    )
    repo.freeze(draft_id=draft.id, actor_id="researcher-1")
    with pytest.raises(ValueError):
        repo.apply_turn(
            draft_id=draft.id,
            user_content="改成只做多",
            output=_output(ready=True),
        )


def test_unfreeze_returns_to_ready_and_clears_hash() -> None:
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    repo.apply_turn(
        draft_id=draft.id,
        user_content="均线金叉买入",
        output=_output(ready=True),
    )
    frozen = repo.freeze(draft_id=draft.id, actor_id="researcher-1")
    assert frozen.state is StrategyDraftState.FROZEN
    assert frozen.content_hash is not None

    unfrozen = repo.unfreeze(draft_id=draft.id, actor_id="researcher-1")
    assert unfrozen.state is StrategyDraftState.READY
    assert unfrozen.content_hash is None
    assert unfrozen.ready is True
    assert unfrozen.code is not None  # 代码与对话保留，仅解除冻结


def test_unfreeze_requires_frozen() -> None:
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    repo.apply_turn(
        draft_id=draft.id,
        user_content="均线金叉买入",
        output=_output(ready=True),
    )
    with pytest.raises(ValueError):
        repo.unfreeze(draft_id=draft.id, actor_id="researcher-1")


def test_list_drafts_filters_by_state_and_owner() -> None:
    repo = make_repository()
    mine = repo.create_draft(actor_id="researcher-1", market="CN_A")
    repo.apply_turn(
        draft_id=mine.id,
        user_content="均线金叉买入",
        output=_output(ready=True),
    )
    repo.freeze(draft_id=mine.id, actor_id="researcher-1")

    other = repo.create_draft(actor_id="researcher-2", market="CN_A")
    repo.apply_turn(
        draft_id=other.id,
        user_content="均线金叉买入",
        output=_output(ready=True),
    )
    repo.freeze(draft_id=other.id, actor_id="researcher-2")

    frozen = repo.list_drafts(owner="researcher-1", state=StrategyDraftState.FROZEN)
    assert [draft.id for draft in frozen] == [mine.id]
    assert other.id not in {draft.id for draft in frozen}

    unfrozen = repo.create_draft(actor_id="researcher-1", market="CN_A")
    assert all(
        draft.id != unfrozen.id
        for draft in repo.list_drafts(
            owner="researcher-1", state=StrategyDraftState.FROZEN
        )
    )


def test_save_draft_snapshots_at_any_step_without_freezing() -> None:
    """保存是任意阶段能力：不 ready 也能保存，且不改动 state。"""
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    repo.apply_turn(
        draft_id=draft.id,
        user_content="均线金叉买入",
        output=_output(ready=False),
    )
    saved = repo.save_draft(draft_id=draft.id, actor_id="researcher-1")
    assert saved.state == StrategyDraftState.DRAFT  # 保存不改动状态
    assert len(saved.saved_versions) == 1
    version = saved.saved_versions[0]
    assert version["version"] == 1
    assert version["hash"]
    assert version["state"] == "DRAFT"
    assert version["title"] == "MA cross"
    assert version["saved_at"]

    # 再次保存累加版本号，且内容指纹一致（内容未变）
    again = repo.save_draft(draft_id=draft.id, actor_id="researcher-1")
    assert len(again.saved_versions) == 2
    assert again.saved_versions[1]["version"] == 2
    assert again.saved_versions[0]["hash"] == again.saved_versions[1]["hash"]


def test_create_draft_defaults_to_strategy_kind_and_empty_evidence() -> None:
    """研究容器默认 kind=strategy，且生命周期证据字段为空。"""
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    assert draft.kind == "strategy"
    assert draft.code_test_result is None
    assert draft.backtest_results == []
    assert draft.paper_binding is None


def test_record_code_test_persists_gate_evidence() -> None:
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    recorded = repo.record_code_test(
        draft_id=draft.id,
        result={"passed": True, "exit_code": 0, "stderr": "", "duration_ms": 42},
    )
    assert recorded.code_test_result is not None
    assert recorded.code_test_result["passed"] is True
    assert recorded.code_test_result["duration_ms"] == 42


def test_record_backtest_appends_traceable_history() -> None:
    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    repo.record_backtest(
        draft_id=draft.id,
        result={
            "backtest_hash": "abc123",
            "start": "2025-01-01",
            "end": "2026-01-01",
            "frequency": "1d",
            "metrics": {"total_return": 0.1},
        },
    )
    updated = repo.record_backtest(
        draft_id=draft.id,
        result={
            "backtest_hash": "def456",
            "start": "2025-06-01",
            "end": "2026-06-01",
            "frequency": "1d",
            "metrics": {"total_return": -0.05},
        },
    )
    assert len(updated.backtest_results) == 2
    assert updated.backtest_results[0]["backtest_hash"] == "abc123"
    assert updated.backtest_results[1]["backtest_hash"] == "def456"
    assert updated.backtest_results[1]["ran_at"]


def test_record_paper_binding_sets_binding() -> None:
    from datetime import UTC, datetime

    repo = make_repository()
    draft = repo.create_draft(actor_id="researcher-1", market="CN_A")
    published_at = datetime.now(UTC)
    updated = repo.record_paper_binding(
        draft_id=draft.id, account_id="pa_1", published_at=published_at
    )
    assert updated.paper_binding == {
        "account_id": "pa_1",
        "published_at": published_at.isoformat(),
    }
