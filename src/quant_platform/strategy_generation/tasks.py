"""回测任务化：配置驱动、幂等、每次独立引擎（对齐 NT BacktestNode）。

任务表 ``backtest_tasks`` 记录声明式 ``BacktestRequest``（内容寻址），后台
线程池逐任务新建引擎运行，结果以统一报告 JSON 存 MinIO（content-addressed）。
同步入口（``:backtest``）保持不变；批量矩阵（``:matrix``）走本服务。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from quant_platform.artifacts.store import canonical_bytes
from quant_platform.research.models import BacktestTaskModel
from quant_platform.strategy_generation.backtest import BacktestRequest
from quant_platform.strategy_generation.repository import SqlAlchemyStrategyRepository
from quant_platform.strategy_generation.service import StrategyBacktestService


def _now() -> datetime:
    return datetime.now(UTC)


class BacktestTaskError(RuntimeError):
    """Raised when a backtest task cannot be created or run."""


class BacktestTaskService:
    """回测任务的创建（幂等）与后台执行。"""

    def __init__(
        self,
        *,
        sessions: sessionmaker[Session],
        artifact_store: Any,
        backtest_service: StrategyBacktestService,
        drafts: SqlAlchemyStrategyRepository,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._sessions = sessions
        self._artifacts = artifact_store
        self._backtest = backtest_service
        self._drafts = drafts
        self._executor = executor or ThreadPoolExecutor(max_workers=2)

    def _payload(self, model: BacktestTaskModel) -> dict[str, Any]:
        return {
            "id": model.id,
            "owner": model.owner,
            "request_hash": model.request_hash,
            "status": model.status,
            "request": model.request,
            "result_address": model.result_address,
            "error": model.error,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
        }

    def create(self, *, actor_id: str, request: BacktestRequest) -> dict[str, Any]:
        """创建回测任务；同 request_hash 幂等（返回既有任务）。"""
        request_hash = request.content_hash()
        now = _now()
        req_dict = request.to_dict()
        task_id = f"bt_{uuid4().hex}"
        with self._sessions.begin() as session:
            existing = session.scalars(
                select(BacktestTaskModel).where(
                    BacktestTaskModel.request_hash == request_hash
                )
            ).first()
            if existing is not None:
                return self._payload(existing)
            session.add(
                BacktestTaskModel(
                    id=task_id,
                    owner=actor_id,
                    request_hash=request_hash,
                    status="PENDING",
                    request=req_dict,
                    created_at=now,
                    updated_at=now,
                )
            )
        self._executor.submit(self._run, task_id, req_dict)
        return {
            "id": task_id,
            "owner": actor_id,
            "request_hash": request_hash,
            "status": "PENDING",
            "request": req_dict,
            "result_address": None,
            "error": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

    def get(self, task_id: str) -> dict[str, Any] | None:
        """任务状态 + 报告（DONE 从 MinIO 读，统一报告 schema）。"""
        with self._sessions.begin() as session:
            model = session.get(BacktestTaskModel, task_id)
            if model is None:
                return None
            payload = self._payload(model)
            status = model.status
            result_address = model.result_address
        if status == "DONE" and result_address:
            raw = self._artifacts.get(result_address)
            import json

            payload["result"] = json.loads(raw.decode())
        return payload

    def list_tasks(
        self, *, actor_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        with self._sessions.begin() as session:
            stmt = select(BacktestTaskModel).where(BacktestTaskModel.owner == actor_id)
            if status is not None:
                stmt = stmt.where(BacktestTaskModel.status == status)
            stmt = stmt.order_by(BacktestTaskModel.created_at.desc())
            return [self._payload(model) for model in session.scalars(stmt).all()]

    def create_matrix(
        self,
        *,
        actor_id: str,
        base: BacktestRequest,
        variations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """批量矩阵：每个 variation 覆盖 request 字段，各开一个独立任务。"""
        tasks: list[dict[str, Any]] = []
        for variation in variations:
            data = base.to_dict()
            data.update(variation)
            request = BacktestRequest.from_dict(data)
            tasks.append(self.create(actor_id=actor_id, request=request))
        return tasks

    # -- 执行 -------------------------------------------------------------

    def _run(self, task_id: str, request_dict: dict[str, Any]) -> None:
        self._update(task_id, status="RUNNING", error=None)
        try:
            request = BacktestRequest.from_dict(request_dict)
            draft = self._drafts.get_draft(request.draft_id)
            if draft is None or draft.code is None:
                raise BacktestTaskError(
                    f"draft {request.draft_id} has no executable code"
                )
            payload = self._backtest.run(
                code=draft.code,
                market=request.market,
                instrument_ids=request.instrument_ids,
                frequency=request.frequency,
                trend_frequency=request.trend_frequency,
                start=request.start,
                end=request.end,
                initial_cash=request.initial_cash,
                venue_spec=request.venue_spec,
            )
            if payload.get("error"):
                raise BacktestTaskError(str(payload["error"]))
            manifest = self._artifacts.put(
                canonical_bytes(payload), media_type="application/json"
            )
            self._update(task_id, status="DONE", result_address=manifest.content_hash)
        except Exception as exc:  # noqa: BLE001
            self._update(task_id, status="FAILED", error=str(exc))

    def _update(
        self,
        task_id: str,
        *,
        status: str,
        error: str | None = None,
        result_address: str | None = None,
    ) -> None:
        with self._sessions.begin() as session:
            model = session.get(BacktestTaskModel, task_id)
            if model is None:
                return
            model.status = status
            model.error = error
            if result_address is not None:
                model.result_address = result_address
            model.updated_at = _now()
