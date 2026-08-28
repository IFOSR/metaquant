"""HTTP API for paper trading account lifecycle (runtime wiring comes later)."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Header

from quant_platform.artifacts.store import ArtifactManifest
from quant_platform.paper.artifact import StrategyArtifactStore
from quant_platform.paper.contracts import PaperAccount, PaperAccountError
from quant_platform.paper.drift import compute_drift
from quant_platform.paper.repository import SqlAlchemyPaperRepository
from quant_platform.paper.service import PaperAccountService
from quant_platform.research.api import (
    ProblemError,
    ResearchPrincipal,
    ResearchPrincipalProvider,
)
from quant_platform.strategy_generation.repository import SqlAlchemyStrategyRepository

# 心跳窗口：最近一次周期落库在此时长内视为节点「仍在跑」。
_RUN_HEARTBEAT_WINDOW = timedelta(minutes=5)

# 本地演示路径：记录 :start-node 拉起的子进程 PID，供 :stop-node 优雅停。
_NODE_PROCESSES: dict[str, int] = {}


def build_paper_router(
    repository: SqlAlchemyPaperRepository,
    principal_provider: ResearchPrincipalProvider,
    drafts: SqlAlchemyStrategyRepository,
    artifact_store: StrategyArtifactStore | None = None,
    backtest_service: Any | None = None,
) -> APIRouter:
    service = PaperAccountService(
        repository=repository,
        artifacts=artifact_store or StrategyArtifactStore(_NullArtifactStore()),
        drafts=drafts,
    )
    router = APIRouter(prefix="/v1/paper", tags=["Paper"])

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

    def _authorize(market: str, actor: ResearchPrincipal, write: bool) -> None:
        scopes = {"paper.write"} if write else {"paper.read"}
        if not actor.can(scopes, project_id="local", market=market):
            raise _not_found()

    def _not_found() -> ProblemError:
        return ProblemError(
            status=404,
            code="PAPER_ACCOUNT_NOT_FOUND",
            title="Paper account not found",
            detail="No paper account exists with this id, or you lack access.",
        )

    def _get_owned(account_id: str, actor: ResearchPrincipal) -> PaperAccount:
        account = service.get_account(account_id)
        if account is None:
            raise _not_found()
        _authorize(account.market, actor, write=False)
        return account

    @router.post("/accounts", status_code=201)
    def create_account(
        command: dict[str, Any],
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        draft_id = str(command.get("draft_id", ""))
        if not draft_id:
            raise ProblemError(
                status=422,
                code="DRAFT_ID_REQUIRED",
                title="draft_id is required",
                detail="Provide the id of a FROZEN strategy draft.",
            )
        raw_cash = command.get("initial_cash")
        initial_cash: Decimal | None = None
        if raw_cash is not None:
            try:
                initial_cash = Decimal(str(raw_cash))
            except InvalidOperation as exc:
                raise ProblemError(
                    status=422,
                    code="INVALID_INITIAL_CASH",
                    title="initial_cash must be a positive decimal",
                    detail=str(exc),
                ) from exc
        try:
            account = service.create_account(
                actor_id=actor.actor_id,
                draft_id=draft_id,
                initial_cash=initial_cash,
            )
        except KeyError as exc:
            raise _not_found() from exc
        except PaperAccountError as exc:
            raise ProblemError(
                status=409,
                code="PAPER_ACCOUNT_REJECTED",
                title="Paper account rejected",
                detail=str(exc),
            ) from exc
        _authorize(account.market, actor, write=True)
        # 发布语义：记录「回测通过 → 仿真账户」绑定，让研究进入 PAPER_LINKED 阶段。
        drafts.record_paper_binding(
            draft_id=draft_id,
            account_id=account.id,
            published_at=account.created_at,
        )
        return account.payload()

    @router.get("/accounts")
    def list_accounts(
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        accounts = [
            account.payload() for account in service.list_accounts(owner=actor.actor_id)
        ]
        return {"accounts": accounts}

    @router.get("/accounts/{account_id}")
    def get_account(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        account = _get_owned(account_id, actor)
        return account.payload()

    @router.post("/accounts/{account_id}:pause")
    def pause_account(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        return _transition(account_id, "pause", actor)

    @router.post("/accounts/{account_id}:resume")
    def resume_account(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        return _transition(account_id, "resume", actor)

    @router.post("/accounts/{account_id}:close")
    def close_account(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        return _transition(account_id, "close", actor)

    def _transition(
        account_id: str, action: str, actor: ResearchPrincipal
    ) -> dict[str, Any]:
        existing = service.get_account(account_id)
        if existing is None:
            raise _not_found()
        _authorize(existing.market, actor, write=True)
        try:
            account = service.transition(account_id=account_id, action=action)
        except (KeyError, PaperAccountError) as exc:
            raise ProblemError(
                status=409,
                code="PAPER_ACCOUNT_TRANSITION_INVALID",
                title="Invalid lifecycle transition",
                detail=str(exc),
            ) from exc
        return account.payload()

    @router.get("/accounts/{account_id}/orders")
    def list_orders(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        _get_owned(account_id, actor)
        return {"orders": repository.list_orders(account_id)}

    @router.get("/accounts/{account_id}/fills")
    def list_fills(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        _get_owned(account_id, actor)
        return {"fills": repository.list_fills(account_id)}

    @router.get("/accounts/{account_id}/positions")
    def list_positions(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        _get_owned(account_id, actor)
        return {"positions": repository.list_positions(account_id)}

    @router.get("/accounts/{account_id}/equity")
    def list_equity(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        _get_owned(account_id, actor)
        return {"equity": repository.list_equity(account_id)}

    @router.get("/accounts/{account_id}/run-status")
    def run_status(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        _get_owned(account_id, actor)
        state = repository.get_run_state(account_id)
        if state is None:
            return {
                "account_id": account_id,
                "status": "OFFLINE",
                "cycles_total": 0,
                "bars_total": 0,
                "last_cycle_at": None,
                "last_bar_at": None,
                "last_error": None,
                "node_running": False,
                "warmed_up": False,
                "updated_at": None,
            }
        last_cycle = state.get("last_cycle_at")
        node_running = False
        if isinstance(last_cycle, str):
            try:
                refreshed = datetime.fromisoformat(last_cycle)
                node_running = datetime.now(UTC) - refreshed < _RUN_HEARTBEAT_WINDOW
            except ValueError:
                node_running = False
        return {
            **state,
            "node_running": node_running,
            "warmed_up": state.get("status") == "LIVE",
        }

    @router.post("/accounts/{account_id}:start-node")
    def start_node(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        account = _get_owned(account_id, actor)
        if account.state.value != "ACTIVE":
            raise ProblemError(
                status=409,
                code="PAPER_ACCOUNT_NOT_ACTIVE",
                title="Paper account is not active",
                detail="Only ACTIVE paper accounts can start a simulation node.",
            )
        state = repository.get_run_state(account_id)
        last_cycle = state.get("last_cycle_at") if state else None
        if isinstance(last_cycle, str):
            try:
                refreshed = datetime.fromisoformat(last_cycle)
                if datetime.now(UTC) - refreshed < _RUN_HEARTBEAT_WINDOW:
                    raise ProblemError(
                        status=409,
                        code="PAPER_NODE_ALREADY_RUNNING",
                        title="Simulation node already running",
                        detail="This account's simulation node is already live.",
                    )
            except ValueError:
                pass
        # 在 api 容器内以子进程方式常驻运行该账户的仿真节点（本地/演示用途）。
        process = subprocess.Popen(
            [sys.executable, "scripts/paper-node.py", "--account-id", account_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _NODE_PROCESSES[account_id] = process.pid
        return {"account_id": account_id, "starting": True}

    @router.post("/accounts/{account_id}:stop-node")
    def stop_node(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        _get_owned(account_id, actor)
        pid = _NODE_PROCESSES.pop(account_id, None)
        if pid is None:
            raise ProblemError(
                status=409,
                code="PAPER_NODE_NOT_RUNNING",
                title="No local simulation node to stop",
                detail="This account has no locally-spawned simulation node; "
                "if it was started via compose, stop it with "
                "`docker compose --profile paper stop paper-node`.",
            )
        with contextlib.suppress(ProcessLookupError, PermissionError):
            # start_new_session=True → 子进程是会话组长，杀整个进程组。
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        return {"account_id": account_id, "stopping": True}

    @router.get("/accounts/{account_id}/drift")
    def drift_report(
        account_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        account = _get_owned(account_id, actor)
        if backtest_service is None:
            raise ProblemError(
                status=503,
                code="DRIFT_UNAVAILABLE",
                title="Drift unavailable",
                detail="The strategy backtest service is not configured.",
            )
        equity_rows = repository.list_equity(account_id)
        if not equity_rows:
            raise ProblemError(
                status=409,
                code="NO_PAPER_EQUITY",
                title="No paper equity yet",
                detail="The account has no reconciled equity snapshots to compare.",
            )
        start = datetime.fromisoformat(equity_rows[0]["trade_date"]).date()  # type: ignore[arg-type]
        try:
            payload = backtest_service.run(
                code=_frozen_code(account),
                market=account.market,
                instrument_ids=tuple(account.instrument_ids),
                frequency=account.frequency,
                start=start,
                end=None,
                initial_cash=Decimal(str(account.initial_cash)),
            )
        except ValueError as exc:
            raise ProblemError(
                status=409,
                code="DRIFT_BACKTEST_NO_DATA",
                title="No backtest data for the paper window",
                detail=str(exc),
            ) from exc
        if not isinstance(payload, dict) or "error" in payload:
            raise ProblemError(
                status=502,
                code="DRIFT_BACKTEST_FAILED",
                title="Baseline backtest failed",
                detail=str(payload.get("error", "unknown"))
                if isinstance(payload, dict)
                else "unknown",
            )
        return compute_drift(
            backtest_payload=payload,
            paper_equity=list(equity_rows),
        )

    def _frozen_code(account: PaperAccount) -> str:
        assert artifact_store is not None
        return artifact_store.load(account.artifact_address).code

    return router


class _NullArtifactStore:
    """Placeholder satisfying the ArtifactStore shape without MinIO (tests)."""

    def put(
        self, payload: bytes, *, media_type: str
    ) -> ArtifactManifest:  # pragma: no cover
        raise RuntimeError("artifact store not configured")

    def get(self, address: str) -> bytes:  # pragma: no cover
        raise RuntimeError("artifact store not configured")

    def exists(self, address: str) -> bool:  # pragma: no cover
        return False

    def verify(self, manifest: ArtifactManifest) -> bool:  # pragma: no cover
        return False
