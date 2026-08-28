"""Persistence for natural-language strategy drafts (G19-P1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from quant_platform.experiments import canonical_hash
from quant_platform.research.models import (
    StrategyDraftModel,
    StrategyMessageModel,
)
from quant_platform.strategy_generation.schemas import (
    AgentOutput,
    BacktestPlan,
    StrategyDraftState,
)


def _now() -> datetime:
    return datetime.now(UTC)


def assistant_reply(output: AgentOutput) -> str:
    """Human-facing assistant message derived from the agent output."""
    if output.question:
        return f"{output.explanation}\n\n{output.question}"
    return output.explanation


def _content_hash(output: AgentOutput) -> str:
    payload = {
        "title": output.title,
        "explanation": output.explanation,
        "code": output.code,
        "instrument_ids": output.instrument_ids,
        "frequency": output.frequency,
        "backtest_plan": (
            output.backtest_plan.model_dump(mode="json")
            if output.backtest_plan is not None
            else None
        ),
    }
    return canonical_hash(payload)


def _draft_hash(
    *,
    title: str,
    explanation: str,
    code: str | None,
    instrument_ids: list[str],
    frequency: str,
    backtest_plan: dict[str, Any] | None,
) -> str:
    """从已持久化的草稿字段计算内容指纹（与 ``_content_hash`` 同构）。"""
    return canonical_hash(
        {
            "title": title,
            "explanation": explanation,
            "code": code,
            "instrument_ids": instrument_ids,
            "frequency": frequency,
            "backtest_plan": backtest_plan,
        }
    )


class SqlAlchemyStrategyRepository:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create_draft(self, *, actor_id: str, market: str) -> StrategyDraftModel:
        timestamp = _now()
        model = StrategyDraftModel(
            id=f"sd_{uuid4().hex}",
            owner=actor_id,
            market=market,
            kind="strategy",
            state=StrategyDraftState.DRAFT,
            title="",
            explanation="",
            question="",
            code=None,
            ready=False,
            instrument_ids=[],
            frequency="1d",
            backtest_plan=None,
            code_test_result=None,
            backtest_results=[],
            paper_binding=None,
            content_hash=None,
            resource_version=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._sessions.begin() as session:
            session.add(model)
        return model

    def get_draft(self, draft_id: str) -> StrategyDraftModel | None:
        with self._sessions.begin() as session:
            return session.get(StrategyDraftModel, draft_id)

    def list_drafts(
        self,
        *,
        owner: str,
        state: StrategyDraftState | None = None,
    ) -> list[StrategyDraftModel]:
        """列出某用户的策略草稿，按最近更新倒序，可按状态过滤。"""
        with self._sessions.begin() as session:
            stmt = select(StrategyDraftModel).where(StrategyDraftModel.owner == owner)
            if state is not None:
                stmt = stmt.where(StrategyDraftModel.state == state)
            stmt = stmt.order_by(StrategyDraftModel.updated_at.desc())
            return list(session.scalars(stmt).all())

    def list_messages(self, draft_id: str) -> list[StrategyMessageModel]:
        with self._sessions.begin() as session:
            rows = session.scalars(
                select(StrategyMessageModel)
                .where(StrategyMessageModel.draft_id == draft_id)
                .order_by(StrategyMessageModel.ordinal)
            ).all()
            return list(rows)

    def apply_turn(
        self,
        *,
        draft_id: str,
        user_content: str,
        output: AgentOutput,
        attachments: list[dict[str, Any]] | None = None,
    ) -> StrategyDraftModel:
        """Atomically append both messages and update the draft from the output."""
        timestamp = _now()
        with self._sessions.begin() as session:
            draft = session.get(StrategyDraftModel, draft_id)
            if draft is None:
                raise KeyError(f"draft not found: {draft_id}")
            if draft.state == StrategyDraftState.FROZEN:
                raise ValueError("draft is frozen; conversation turns are rejected")
            next_ordinal = (
                session.query(StrategyMessageModel)
                .filter(StrategyMessageModel.draft_id == draft_id)
                .count()
            )
            session.add(
                StrategyMessageModel(
                    id=f"sm_{uuid4().hex}",
                    draft_id=draft_id,
                    ordinal=next_ordinal,
                    role="user",
                    content=user_content,
                    attachments=attachments or [],
                    created_at=timestamp,
                )
            )
            session.add(
                StrategyMessageModel(
                    id=f"sm_{uuid4().hex}",
                    draft_id=draft_id,
                    ordinal=next_ordinal + 1,
                    role="assistant",
                    content=assistant_reply(output),
                    created_at=timestamp,
                )
            )
            draft.title = output.title
            draft.explanation = output.explanation
            draft.question = output.question
            draft.code = output.code
            draft.ready = output.ready
            draft.instrument_ids = output.instrument_ids
            draft.frequency = output.frequency
            draft.kind = output.kind
            draft.backtest_plan = (
                output.backtest_plan.model_dump(mode="json")
                if output.backtest_plan is not None
                else None
            )
            # 代码被改写后，旧的「代码正确性测试」证据失效，须重跑门禁。
            draft.code_test_result = None
            draft.state = (
                StrategyDraftState.READY if output.ready else StrategyDraftState.DRAFT
            )
            draft.resource_version += 1
            draft.updated_at = timestamp
            return draft

    def freeze(self, *, draft_id: str, actor_id: str) -> StrategyDraftModel:
        """Freeze a ready draft, recording its content hash."""
        del actor_id  # reserved for audit wiring
        timestamp = _now()
        with self._sessions.begin() as session:
            draft = session.get(StrategyDraftModel, draft_id)
            if draft is None:
                raise KeyError(f"draft not found: {draft_id}")
            if not draft.ready or draft.code is None or not draft.instrument_ids:
                raise ValueError(
                    "draft is not ready to freeze (needs code + instruments)"
                )
            output = AgentOutput(
                title=draft.title,
                explanation=draft.explanation,
                question=draft.question,
                code=draft.code,
                ready=True,
                instrument_ids=draft.instrument_ids,
                frequency=draft.frequency,
                backtest_plan=(
                    BacktestPlan.model_validate(draft.backtest_plan)
                    if draft.backtest_plan is not None
                    else None
                ),
            )
            draft.content_hash = _content_hash(output)
            draft.state = StrategyDraftState.FROZEN
            draft.resource_version += 1
            draft.updated_at = timestamp
            return draft

    def unfreeze(self, *, draft_id: str, actor_id: str) -> StrategyDraftModel:
        """把冻结草稿退回可编辑态（清空内容指纹，保留代码与对话）。

        冻结是内容寻址的不可变快照；用户要「继续编辑」时需显式解除冻结，
        此时 content_hash 失效（后续再冻结会重新计算）。
        """
        del actor_id  # reserved for audit wiring
        timestamp = _now()
        with self._sessions.begin() as session:
            draft = session.get(StrategyDraftModel, draft_id)
            if draft is None:
                raise KeyError(f"draft not found: {draft_id}")
            if draft.state != StrategyDraftState.FROZEN:
                raise ValueError("draft is not frozen")
            draft.state = StrategyDraftState.READY
            draft.content_hash = None
            draft.resource_version += 1
            draft.updated_at = timestamp
            return draft

    def save_draft(self, *, draft_id: str, actor_id: str) -> StrategyDraftModel:
        """保存一个版本化快照（任意阶段可用，不改变 state）。

        「保存」不是终点：每次保存追加一条不可变版本记录（内容指纹 + 状态 +
        时间 + 标题），用于回滚与追溯；草稿本身依旧实时落库。
        """
        del actor_id  # reserved for audit wiring
        timestamp = _now()
        with self._sessions.begin() as session:
            draft = session.get(StrategyDraftModel, draft_id)
            if draft is None:
                raise KeyError(f"draft not found: {draft_id}")
            versions = list(draft.saved_versions or [])
            versions.append(
                {
                    "version": len(versions) + 1,
                    "hash": _draft_hash(
                        title=draft.title,
                        explanation=draft.explanation,
                        code=draft.code,
                        instrument_ids=draft.instrument_ids,
                        frequency=draft.frequency,
                        backtest_plan=draft.backtest_plan,
                    ),
                    "state": draft.state,
                    "title": draft.title,
                    "saved_at": timestamp.isoformat(),
                }
            )
            draft.saved_versions = versions
            draft.resource_version += 1
            draft.updated_at = timestamp
            return draft

    def record_code_test(
        self, *, draft_id: str, result: dict[str, Any]
    ) -> StrategyDraftModel:
        """记录代码正确性测试结果（非回测），并作为「去回测」的门禁证据。"""
        timestamp = _now()
        with self._sessions.begin() as session:
            draft = session.get(StrategyDraftModel, draft_id)
            if draft is None:
                raise KeyError(f"draft not found: {draft_id}")
            draft.code_test_result = result
            draft.resource_version += 1
            draft.updated_at = timestamp
            return draft

    def record_backtest(
        self, *, draft_id: str, result: dict[str, Any]
    ) -> StrategyDraftModel:
        """把一次回测结果追加进可追溯历史（含 backtest_hash）。"""
        timestamp = _now()
        with self._sessions.begin() as session:
            draft = session.get(StrategyDraftModel, draft_id)
            if draft is None:
                raise KeyError(f"draft not found: {draft_id}")
            history = list(draft.backtest_results or [])
            history.append(
                {
                    "backtest_hash": result.get("backtest_hash", ""),
                    "start": result.get("start", ""),
                    "end": result.get("end", ""),
                    "frequency": result.get("frequency", ""),
                    "metrics": result.get("metrics"),
                    "ran_at": timestamp.isoformat(),
                }
            )
            draft.backtest_results = history
            draft.resource_version += 1
            draft.updated_at = timestamp
            return draft

    def record_paper_binding(
        self, *, draft_id: str, account_id: str, published_at: datetime
    ) -> StrategyDraftModel:
        """记录「回测通过 → 发布仿真」的账户绑定。"""
        timestamp = _now()
        with self._sessions.begin() as session:
            draft = session.get(StrategyDraftModel, draft_id)
            if draft is None:
                raise KeyError(f"draft not found: {draft_id}")
            draft.paper_binding = {
                "account_id": account_id,
                "published_at": published_at.isoformat(),
            }
            draft.resource_version += 1
            draft.updated_at = timestamp
            return draft
