"""HTTP API for natural-language strategy drafts (G19-P1)."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

from fastapi import APIRouter, Depends, File, Header, UploadFile

from quant_platform.artifacts import ArtifactStore
from quant_platform.experiment_runtime.execution_state_service import (
    ExecutionStateService,
)
from quant_platform.research.api import (
    ProblemError,
    ResearchPrincipal,
    ResearchPrincipalProvider,
)
from quant_platform.research.attachment import extract_attachment
from quant_platform.research.factor_extract import Runner
from quant_platform.research.models import StrategyDraftModel, StrategyMessageModel
from quant_platform.strategy_generation.agent import (
    AgentOutput,
    run_turn,
)
from quant_platform.strategy_generation.backtest import (
    BacktestRequest,
    code_test_strategy,
)
from quant_platform.strategy_generation.provisioning import (
    StrategyDataProvisioner,
    StrategyProvisionError,
)
from quant_platform.strategy_generation.repository import (
    SqlAlchemyStrategyRepository,
)
from quant_platform.strategy_generation.schemas import (
    FREQUENCY_SET,
    CreateStrategyDraftCommand,
    PostStrategyMessageCommand,
    StrategyDraftState,
    StrategyMessage,
)
from quant_platform.strategy_generation.service import StrategyBacktestService
from quant_platform.strategy_generation.tasks import BacktestTaskService


def _attachment_text(attachments: list[dict[str, Any]]) -> str:
    """把附件序列化为注入 Agent 提示的文本块（文本直接贴内容，图片记引用）。"""
    parts: list[str] = []
    for att in attachments or []:
        name = str(att.get("name", ""))
        kind = att.get("kind", "text")
        extracted = str(att.get("extracted_text", "") or "").strip()
        if kind == "text" and extracted:
            parts.append(f"[附件：{name}]\n{extracted}")
        else:
            parts.append(f"[附件：{name}]")
    return "\n\n".join(parts)


def _history(messages: list[StrategyMessageModel]) -> list[StrategyMessage]:
    """重建 Agent 视角的会话历史：用户消息补上其附件抽取文本。"""
    history: list[StrategyMessage] = []
    for message in messages:
        content = message.content
        if message.role == "user":
            extra = _attachment_text(message.attachments)
            if extra:
                content = f"{content}\n\n{extra}"
        history.append(StrategyMessage(role=message.role, content=content))
    return history


def _research_stage(record: StrategyDraftModel) -> str:
    """从证据字段派生研究生命周期阶段（CREATING→…→PAPER_LINKED）。"""
    if record.paper_binding:
        return "PAPER_LINKED"
    if record.backtest_results:
        return "BACKTESTED"
    if record.code_test_result and record.code_test_result.get("passed"):
        return "CODE_TESTED"
    if record.ready:
        return "READY"
    return "CREATING"


def _draft_snapshot(record: StrategyDraftModel) -> dict[str, Any]:
    return {
        "id": record.id,
        "market": record.market,
        "kind": record.kind,
        "stage": _research_stage(record),
        "state": record.state,
        "title": record.title,
        "explanation": record.explanation,
        "question": record.question,
        "code": record.code,
        "ready": record.ready,
        "instrument_ids": record.instrument_ids,
        "frequency": record.frequency,
        "backtest_plan": record.backtest_plan,
        "code_test_result": record.code_test_result,
        "backtest_results": record.backtest_results,
        "paper_binding": record.paper_binding,
        "content_hash": record.content_hash,
        "saved_versions": record.saved_versions,
        "resource_version": record.resource_version,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _error_payload(exc: Exception, draft: StrategyDraftModel) -> dict[str, Any]:
    """错误时仍返回与成功一致的回测 payload 结构（前端统一渲染）。"""
    return {
        "schema_version": "strategy-backtest/v1",
        "instrument_ids": list(draft.instrument_ids),
        "start": "",
        "end": "",
        "frequency": draft.frequency,
        "initial_cash": 0.0,
        "gross_of_fees": True,
        "metrics": {
            "total_return": 0.0,
            "sharpe": None,
            "max_drawdown": 0.0,
            "trade_count": 0,
        },
        "equity_curve": [],
        "trades": [],
        "positions": [],
        "backtest_hash": "",
        "error": str(exc),
    }


def build_strategy_router(
    repository: SqlAlchemyStrategyRepository,
    principal_provider: ResearchPrincipalProvider,
    runner: Runner | None = None,
    backtest_service: StrategyBacktestService | None = None,
    execution_state: ExecutionStateService | None = None,
    provisioner: StrategyDataProvisioner | None = None,
    task_service: BacktestTaskService | None = None,
    attachment_store: ArtifactStore | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["StrategyDrafts"])

    def principal(
        authorization: str | None = Header(default=None),
    ) -> ResearchPrincipal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise ProblemError(
                status=401,
                code="AUTHENTICATION_REQUIRED",
                title="Authentication required",
                detail="A Bearer access token is required.",
            )
        resolved = principal_provider(authorization.removeprefix("Bearer ").strip())
        if resolved is None:
            raise ProblemError(
                status=401,
                code="INVALID_ACCESS_TOKEN",
                title="Invalid access token",
                detail="The supplied access token is not recognized.",
            )
        return resolved

    def _authorize_write(market: str, actor: ResearchPrincipal) -> None:
        if not actor.can({"strategy.write"}, project_id="local", market=market):
            raise _not_found()

    def _not_found() -> ProblemError:
        return ProblemError(
            status=404,
            code="STRATEGY_DRAFT_NOT_FOUND",
            title="Strategy draft not found",
            detail="No strategy draft exists with this id, or you lack access.",
        )

    @router.get("/strategy-drafts")
    def list_strategy_drafts(
        state: StrategyDraftState | None = None,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        readable = {
            market
            for project, market in actor.scopes({"strategy.read"})
            if project == "local"
        }
        records = repository.list_drafts(owner=actor.actor_id, state=state)
        return {
            "items": [
                _draft_snapshot(record)
                for record in records
                if record.market in readable
            ]
        }

    @router.post("/strategy-drafts", status_code=202)
    def create_strategy_draft(
        command: CreateStrategyDraftCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        _authorize_write(command.market, actor)
        draft = repository.create_draft(actor_id=actor.actor_id, market=command.market)
        user_content = command.first_message
        extra = _attachment_text(
            [a.model_dump(mode="json") for a in command.attachments]
        )
        if extra:
            user_content = f"{command.first_message}\n\n{extra}"
        output = _run_agent_turn(
            market=command.market,
            history=[StrategyMessage(role="user", content=user_content)],
        )
        updated = repository.apply_turn(
            draft_id=draft.id,
            user_content=command.first_message,
            output=output,
            attachments=[a.model_dump(mode="json") for a in command.attachments],
        )
        return _draft_snapshot(updated)

    @router.post("/strategy-drafts/{draft_id}/messages", status_code=202)
    def post_strategy_message(
        draft_id: str,
        command: PostStrategyMessageCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        _authorize_write(draft.market, actor)
        if draft.state == StrategyDraftState.FROZEN:
            raise ProblemError(
                status=409,
                code="STRATEGY_DRAFT_FROZEN",
                title="Strategy draft is frozen",
                detail="This strategy draft is frozen and read-only. "
                "Start a new conversation to iterate on the strategy.",
            )
        history = _history(repository.list_messages(draft_id))
        user_content = command.message
        extra = _attachment_text(
            [a.model_dump(mode="json") for a in command.attachments]
        )
        if extra:
            user_content = f"{command.message}\n\n{extra}"
        history.append(StrategyMessage(role="user", content=user_content))
        output = _run_agent_turn(market=draft.market, history=history)
        updated = repository.apply_turn(
            draft_id=draft_id,
            user_content=command.message,
            output=output,
            attachments=[a.model_dump(mode="json") for a in command.attachments],
        )
        return _draft_snapshot(updated)

    @router.post("/strategy-drafts/attachments", status_code=200)
    async def upload_strategy_attachment(
        market: str,
        file: UploadFile = File(...),  # noqa: B008
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        """上传对话附件：MinIO 落库（可选）+ 文本抽取 / 图片引用。

        返回 ``{name, kind, object_key, extracted_text}``，前端把它随消息一起
        提交；抽取出的文本会被注入 Agent 提示，图片仅记录 object_key 引用
        （视觉/OCR 见 ``extract_attachment`` 的降级说明）。
        """
        _authorize_write(market, actor)
        content = await file.read()
        name = file.filename or "attachment"
        kind, extracted_text = extract_attachment(name, content)
        object_key = ""
        if attachment_store is not None:
            media_type = file.content_type or (
                "application/octet-stream" if kind == "text" else "image/*"
            )
            object_key = attachment_store.put(
                content, media_type=media_type
            ).content_hash
        return {
            "name": name,
            "kind": kind,
            "object_key": object_key,
            "extracted_text": extracted_text,
        }

    @router.get("/strategy-drafts/{draft_id}")
    def get_strategy_draft(
        draft_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        if not actor.can({"strategy.read"}, project_id="local", market=draft.market):
            raise _not_found()
        messages = [
            {"role": message.role, "content": message.content}
            for message in repository.list_messages(draft_id)
        ]
        snapshot = _draft_snapshot(draft)
        snapshot["messages"] = messages
        return snapshot

    @router.post("/strategy-drafts/{draft_id}:provision", status_code=200)
    def provision_strategy_data(
        draft_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        frequency: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        _authorize_write(draft.market, actor)
        if not draft.instrument_ids:
            raise ProblemError(
                status=409,
                code="STRATEGY_DRAFT_NO_INSTRUMENTS",
                title="Strategy draft has no instruments",
                detail="The strategy must specify instruments before provisioning.",
            )
        if provisioner is None:
            raise ProblemError(
                status=503,
                code="PROVISIONING_UNAVAILABLE",
                title="Data provisioning unavailable",
                detail="On-demand data provisioning is not configured.",
            )
        plan_start, plan_end, plan_frequency, _plan_trend = _plan_defaults(draft)
        target_start = start or plan_start
        target_end = end or plan_end
        # 按基础粒度去重：1w 与 1d 共用日线，15/30/60m 与 5m 共用 5m。
        base_seen: set[str] = set()
        total_rows = 0
        sources: set[str] = set()
        try:
            for selected in _plan_frequencies(draft, frequency):
                base = "1d" if selected in ("1d", "1w") else "5m"
                if base in base_seen:
                    continue
                base_seen.add(base)
                result = provisioner.provision(
                    instrument_ids=tuple(draft.instrument_ids),
                    frequency=selected,
                    start=target_start,
                    end=target_end,
                )
                total_rows += result.rows
                sources.update(result.sources)
        except StrategyProvisionError as exc:
            raise ProblemError(
                status=502,
                code="STRATEGY_PROVISION_FAILED",
                title="Data provisioning failed",
                detail=str(exc),
            ) from exc
        return {
            "instrument_ids": list(draft.instrument_ids),
            "frequency": plan_frequency,
            "rows": total_rows,
            "sources": sorted(sources),
        }

    def _plan_defaults(
        draft: StrategyDraftModel,
    ) -> tuple[date | None, date | None, str, str | None]:
        """从 backtest_plan 取默认起止日期与执行/趋势周期。"""
        plan = draft.backtest_plan or {}

        def _parse(value: object) -> date | None:
            if not isinstance(value, str) or not value:
                return None
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None

        def _freq(value: object) -> str | None:
            return value if isinstance(value, str) and value in FREQUENCY_SET else None

        exec_frequency = _freq(plan.get("exec_timeframe")) or draft.frequency
        trend_frequency = _freq(plan.get("trend_timeframe"))
        if trend_frequency == exec_frequency:
            trend_frequency = None
        return (
            _parse(plan.get("start")),
            _parse(plan.get("end")),
            exec_frequency,
            trend_frequency,
        )

    def _resolve_frequency(draft_frequency: str, override: str | None) -> str:
        if override is None:
            return draft_frequency
        if override not in FREQUENCY_SET:
            raise ProblemError(
                status=422,
                code="INVALID_FREQUENCY",
                title="Invalid frequency",
                detail="frequency must be one of 1d, 1w, 5m, 15m, 30m, 60m.",
            )
        return override

    def _plan_frequencies(
        draft: StrategyDraftModel, override: str | None
    ) -> tuple[str, ...]:
        """数据状态/采集覆盖的频率集合：显式覆盖优先，否则取方案的全部周期。"""
        if override is not None:
            return (_resolve_frequency(draft.frequency, override),)
        plan = draft.backtest_plan or {}
        timeframes = plan.get("timeframes")
        if isinstance(timeframes, list):
            valid = tuple(
                dict.fromkeys(item for item in timeframes if item in FREQUENCY_SET)
            )
            if valid:
                return valid
        return (draft.frequency,)

    @router.get("/strategy-drafts/{draft_id}/data-status")
    def strategy_draft_data_status(
        draft_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        frequency: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        if not actor.can({"strategy.read"}, project_id="local", market=draft.market):
            raise _not_found()
        if backtest_service is None:
            raise ProblemError(
                status=503,
                code="BACKTEST_UNAVAILABLE",
                title="Backtest unavailable",
                detail="The strategy backtest service is not configured.",
            )
        return backtest_service.data_status(
            instrument_ids=tuple(draft.instrument_ids),
            frequencies=_plan_frequencies(draft, frequency),
            start=start,
            end=end,
        )

    @router.post("/strategy-drafts/{draft_id}:save", status_code=200)
    def save_strategy_draft(
        draft_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        """任意阶段保存一个版本化快照（不改动 state，用于回滚/追溯）。"""
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        _authorize_write(draft.market, actor)
        saved = repository.save_draft(draft_id=draft_id, actor_id=actor.actor_id)
        return _draft_snapshot(saved)

    @router.post("/strategy-drafts/{draft_id}:freeze", status_code=202)
    def freeze_strategy_draft(
        draft_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        _authorize_write(draft.market, actor)
        try:
            frozen = repository.freeze(draft_id=draft_id, actor_id=actor.actor_id)
        except ValueError as exc:
            raise ProblemError(
                status=409,
                code="STRATEGY_DRAFT_NOT_READY",
                title="Strategy draft not ready",
                detail=str(exc),
            ) from exc
        return _draft_snapshot(frozen)

    @router.post("/strategy-drafts/{draft_id}:unfreeze", status_code=202)
    def unfreeze_strategy_draft(
        draft_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        _authorize_write(draft.market, actor)
        try:
            unfrozen = repository.unfreeze(draft_id=draft_id, actor_id=actor.actor_id)
        except ValueError as exc:
            raise ProblemError(
                status=409,
                code="STRATEGY_DRAFT_NOT_FROZEN",
                title="Strategy draft not frozen",
                detail=str(exc),
            ) from exc
        return _draft_snapshot(unfrozen)

    @router.post("/strategy-drafts/{draft_id}:backtest", status_code=200)
    def backtest_strategy_draft(
        draft_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        start: date | None = None,
        end: date | None = None,
        frequency: str | None = None,
    ) -> dict[str, Any]:
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        _authorize_write(draft.market, actor)
        if not draft.ready or draft.code is None or not draft.instrument_ids:
            raise ProblemError(
                status=409,
                code="STRATEGY_DRAFT_NOT_READY",
                title="Strategy draft not ready",
                detail="Strategy must be ready with instruments before backtesting.",
            )
        if backtest_service is None:
            raise ProblemError(
                status=503,
                code="BACKTEST_UNAVAILABLE",
                title="Backtest unavailable",
                detail="The strategy backtest service is not configured.",
            )
        plan_start, plan_end, plan_frequency, plan_trend = _plan_defaults(draft)
        # 客户端参数校验放在兜底之外：非法输入必须以 422 Problem 返回，
        # 不能被「生成代码失败的统一 payload」吞成假成功。
        resolved_frequency = _resolve_frequency(plan_frequency, frequency)
        try:
            payload = backtest_service.run(
                code=draft.code,
                market=draft.market,
                instrument_ids=tuple(draft.instrument_ids),
                frequency=resolved_frequency,
                trend_frequency=plan_trend,
                start=start or plan_start,
                end=end or plan_end,
            )
        except Exception as exc:  # noqa: BLE001
            # 生成代码任意失败都以一致的错误 payload 返回，供对话修复。
            return _error_payload(exc, draft)
        # 成功回测沉淀为可追溯历史（含 backtest_hash），供「回测」页对比。
        repository.record_backtest(draft_id=draft_id, result=payload)
        return payload

    @router.get(
        "/strategy-drafts/{draft_id}/backtests/{backtest_hash}", status_code=200
    )
    def get_strategy_backtest_result(
        draft_id: str,
        backtest_hash: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        """按 backtest_hash 重放一次历史回测并返回完整结果（只读，不写入历史）。

        冻结后的策略 code 固定、行情数据确定，同一参数重放会得到同一
        backtest_hash，因此按条目记录的范围重算即可忠实还原当时那次回测。
        """
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        if not actor.can({"strategy.read"}, project_id="local", market=draft.market):
            raise _not_found()
        if not draft.ready or draft.code is None or not draft.instrument_ids:
            raise _not_found()
        if backtest_service is None:
            raise ProblemError(
                status=503,
                code="BACKTEST_UNAVAILABLE",
                title="Backtest unavailable",
                detail="The strategy backtest service is not configured.",
            )
        history = list(draft.backtest_results or [])
        entry = next(
            (
                item
                for item in history
                if str(item.get("backtest_hash", "")) == backtest_hash
            ),
            None,
        )
        if entry is None:
            raise _not_found()

        def _iso_date(value: object) -> date | None:
            if not isinstance(value, str) or not value:
                return None
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None

        plan_start, plan_end, plan_frequency, plan_trend = _plan_defaults(draft)
        entry_frequency = entry.get("frequency")
        frequency = (
            entry_frequency
            if isinstance(entry_frequency, str) and entry_frequency in FREQUENCY_SET
            else plan_frequency
        )
        try:
            return backtest_service.run(
                code=draft.code,
                market=draft.market,
                instrument_ids=tuple(draft.instrument_ids),
                frequency=frequency,
                trend_frequency=plan_trend,
                start=_iso_date(entry.get("start")) or plan_start,
                end=_iso_date(entry.get("end")) or plan_end,
            )
        except Exception as exc:  # noqa: BLE001
            # 与运行一致地返回统一错误 payload，供前端渲染修复提示。
            return _error_payload(exc, draft)

    @router.post("/strategy-drafts/{draft_id}:code-test", status_code=200)
    def code_test_strategy_draft(
        draft_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        """代码正确性测试（非回测）：用「数据准备」的基础行情编译+实例化+跑通。"""
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        _authorize_write(draft.market, actor)
        if not draft.ready or draft.code is None or not draft.instrument_ids:
            raise ProblemError(
                status=409,
                code="STRATEGY_DRAFT_NOT_READY",
                title="Strategy draft not ready",
                detail="Strategy must be ready with instruments before code testing.",
            )
        if backtest_service is None:
            raise ProblemError(
                status=503,
                code="BACKTEST_UNAVAILABLE",
                title="Backtest unavailable",
                detail="The strategy backtest service is not configured.",
            )
        _plan_start, _plan_end, _plan_frequency, plan_trend = _plan_defaults(draft)
        try:
            db_ids, exec_bars, trend_bars = backtest_service.load_code_test_bars(
                instrument_ids=tuple(draft.instrument_ids),
                frequency=draft.frequency,
                trend_frequency=plan_trend,
            )
        except ValueError as exc:
            # 数据未就绪：引导用户先做「数据准备」（采集数据或改用有数据的标的）。
            raise ProblemError(
                status=409,
                code="MARKET_DATA_NOT_READY",
                title="Market data not ready",
                detail=(
                    "该策略所需的行情数据尚未就绪，请先准备数据（采集所需数据，"
                    "或改用有数据的标的/周期）。"
                ),
            ) from exc
        result = code_test_strategy(
            code=draft.code,
            market=draft.market,
            instrument_ids=db_ids,
            bars_by_instrument=exec_bars,
            frequency=draft.frequency,
            trend_bars_by_instrument=trend_bars,
            trend_frequency=plan_trend,
        )
        payload = result.payload()
        repository.record_code_test(draft_id=draft_id, result=payload)
        return payload

    @router.post("/strategy-drafts/{draft_id}:paper", status_code=200)
    def paper_strategy_draft(
        draft_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        draft = repository.get_draft(draft_id)
        if draft is None:
            raise _not_found()
        _authorize_write(draft.market, actor)
        if not draft.ready or draft.code is None or not draft.instrument_ids:
            raise ProblemError(
                status=409,
                code="STRATEGY_DRAFT_NOT_READY",
                title="Strategy draft not ready",
                detail="Strategy must be ready with instruments before paper trading.",
            )
        if backtest_service is None:
            raise ProblemError(
                status=503,
                code="BACKTEST_UNAVAILABLE",
                title="Backtest unavailable",
                detail="The strategy backtest service is not configured.",
            )
        try:
            payload = backtest_service.run(
                code=draft.code,
                market=draft.market,
                instrument_ids=tuple(draft.instrument_ids),
                frequency=draft.frequency,
                start=None,
                end=None,
            )
        except Exception as exc:  # noqa: BLE001
            # 生成代码任意失败都以一致的错误 payload 返回，供对话修复。
            return _error_payload(exc, draft)
        positions = cast("list[dict[str, Any]]", payload.get("positions", []))
        open_positions = {
            position["instrument_id"]: position
            for position in positions
            if position.get("closed_at") is None
        }
        if execution_state is not None:
            execution_state.record_paper_positions(positions=open_positions)
        payload["paper_positions"] = open_positions
        return payload

    @router.post("/strategy-backtests", status_code=202)
    def create_backtest_task(
        command: dict[str, Any],
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if task_service is None:
            raise ProblemError(
                status=503,
                code="BACKTEST_TASKS_UNAVAILABLE",
                title="Backtest tasks unavailable",
                detail="The async backtest task service is not configured.",
            )
        try:
            request = BacktestRequest.from_dict(command)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProblemError(
                status=422,
                code="INVALID_BACKTEST_REQUEST",
                title="Invalid backtest request",
                detail=str(exc),
            ) from exc
        return task_service.create(actor_id=actor.actor_id, request=request)

    @router.post("/strategy-backtests:matrix", status_code=202)
    def create_backtest_matrix(
        command: dict[str, Any],
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if task_service is None:
            raise ProblemError(
                status=503,
                code="BACKTEST_TASKS_UNAVAILABLE",
                title="Backtest tasks unavailable",
                detail="The async backtest task service is not configured.",
            )
        try:
            base = BacktestRequest.from_dict(command["base"])
            variations = command["variations"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProblemError(
                status=422,
                code="INVALID_BACKTEST_REQUEST",
                title="Invalid backtest matrix",
                detail=str(exc),
            ) from exc
        if not isinstance(variations, list) or not variations:
            raise ProblemError(
                status=422,
                code="INVALID_BACKTEST_REQUEST",
                title="Invalid backtest matrix",
                detail="variations must be a non-empty list.",
            )
        return {
            "items": task_service.create_matrix(
                actor_id=actor.actor_id, base=base, variations=variations
            )
        }

    @router.get("/strategy-backtests")
    def list_backtest_tasks(
        state: str | None = None,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if task_service is None:
            return {"items": []}
        return {"items": task_service.list_tasks(actor_id=actor.actor_id, status=state)}

    @router.get("/strategy-backtests/{task_id}")
    def get_backtest_task(
        task_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if task_service is None:
            raise _not_found()
        task = task_service.get(task_id)
        if task is None or task["owner"] != actor.actor_id:
            raise _not_found()
        return task

    def _run_agent_turn(
        *,
        market: str,
        history: list[StrategyMessage],
    ) -> AgentOutput:
        try:
            return run_turn(market=market, history=history, runner=runner)
        except Exception as exc:  # noqa: BLE001
            # LLM 任意失败（含网络超时）都以 502 优雅返回，绝不裸 500。
            raise ProblemError(
                status=502,
                code="STRATEGY_AGENT_FAILED",
                title="Strategy agent failed",
                detail=str(exc),
            ) from exc

    return router
