from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile

from quant_platform.data_gateway.provisioning import (
    DataProvisioning,
    ProvisioningTaskManager,
    ProvisionResult,
)
from quant_platform.data_gateway.universe import UniverseResolver
from quant_platform.experiment_runtime.repository import (
    SqlAlchemyExperimentRepository,
)
from quant_platform.experiment_runtime.schemas import (
    AssessIndependenceCommand,
    AssessRobustnessCommand,
    FromPaperPipelineCommand,
    PreregisterExperimentCommand,
    PromoteCommand,
    ProvisionCommand,
    RunBacktestCommand,
    RunExperimentCommand,
    SignApprovalCommand,
    ValidateExperimentCommand,
)
from quant_platform.experiments import ResourceBudget
from quant_platform.research.api import (
    ProblemError,
    ResearchPrincipal,
    ResearchPrincipalProvider,
)
from quant_platform.research.attachment import (
    parse_attachment,
    resolve_material,
)
from quant_platform.research.factor_extract import (
    FactorExtractionError,
    extract_factor_from_paper,
)
from quant_platform.validation import CandidateEvidence, ICSign


def _pipeline_from_paper(
    repository: SqlAlchemyExperimentRepository,
    *,
    paper_text: str,
    market: str,
    user_prompt: str | None,
    actor_id: str,
    idempotency_key: str,
    request_payload: dict[str, Any],
    horizon: str,
    random_seed: int,
    snapshot_id: str | None,
    snapshot_manifest_hash: str | None,
) -> dict[str, Any]:
    """Extract a factor from a report and drive it to a preregistered experiment."""
    material, resolved_prompt = resolve_material(paper_text, user_prompt)
    extraction = extract_factor_from_paper(
        material, market, user_prompt=resolved_prompt
    )
    factor_ir = extraction.factor_ir
    scope = factor_ir["market_scope"]
    clocks = factor_ir["decision_clock"]

    job = repository._research.create_job(
        actor_id=actor_id,
        project_id="local",
        title=str(factor_ir.get("factor_id", "extracted-factor")),
        market=market,
        universe_ref=str(scope["universe_ref"]),
        frequency=str(scope.get("frequency", "1d")),
        decision_clock=str(clocks["signal_time"]),
        trade_clock=str(clocks["earliest_trade_time"]),
        settlement_clock=(
            "T+1_SETTLEMENT" if market == "CN_COMMODITY_FUTURES" else None
        ),
        exchange_scope=list(scope.get("exchange_scope", [])),
        contract_selection="ACTUAL_CONTRACTS_ONLY",
        roll_policy=str(scope.get("roll_policy_ref", "")),
        horizon=horizon,
        research_brief_version_id="placeholder",
        budget={
            "candidate_limit": 20,
            "llm_token_limit": 120000,
            "cpu_hours": 24,
            "wall_clock_minutes": 60,
        },
    )
    brief = repository._research.create_brief_version(
        job_id=job.id,
        actor_id=actor_id,
        content=extraction.brief,
        expected_job_version=job.resource_version,
    )
    brief = repository._research.freeze_brief(
        brief.id,
        actor_id=actor_id,
        expected_resource_version=brief.resource_version,
    )
    if not snapshot_id or not snapshot_manifest_hash:
        candidates = [
            item
            for item in repository.list_formal_snapshots()
            if item.get("market") == market
        ]
        if not candidates:
            raise ValueError("NO_SNAPSHOT_FOR_MARKET")
        # Prefer the broadest snapshot: cross-sectional IC needs many
        # instruments, and single-contract ad-hoc snapshots produce null ICs.
        match = max(
            candidates,
            key=lambda item: len(item.get("instruments") or []),
        )
        snapshot_id = str(match["snapshot_id"])
        snapshot_manifest_hash = str(match["manifest_hash"])
    label = next(
        (
            item
            for item in repository.list_label_snapshots()
            if item.get("market") == market and item.get("decision_time")
        ),
        None,
    )
    decision_time = (
        datetime.fromisoformat(str(label["decision_time"]))
        if label
        else datetime.now(UTC)
    )
    receipt = repository.preregister(
        actor_id=actor_id,
        project_id="local",
        market=market,
        idempotency_key=idempotency_key,
        request_hash=_request_hash(request_payload),
        reason="from-paper pipeline",
        parent_artifact_id=None,
        research_job_id=job.id,
        brief_version_id=brief.id,
        decision_time=decision_time,
        random_seed=random_seed,
        resource_budget=ResourceBudget(
            cpu_seconds=3600,
            wall_clock_seconds=1800,
            memory_mb=2048,
            max_observations=100000,
        ),
        factor_ir_payload=factor_ir,
        snapshot_id=snapshot_id,
        snapshot_manifest_hash=snapshot_manifest_hash,
    )
    return {
        "job_id": job.id,
        "brief_id": brief.id,
        "experiment_id": receipt.resource_id,
        "brief": extraction.brief.model_dump(mode="json"),
        "factor_ir": factor_ir,
        "explanation": extraction.explanation,
    }


def build_experiment_router(
    repository: SqlAlchemyExperimentRepository,
    principal_provider: ResearchPrincipalProvider,
    provisioning: DataProvisioning | None = None,
    task_manager: ProvisioningTaskManager | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["Experiments"])

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

    @router.post("/research-pipelines:from-paper", status_code=202)
    def create_research_from_paper(
        command: FromPaperPipelineCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
    ) -> dict[str, Any]:
        if not actor.can(
            {"research.jobs.manage", "research.experiments.preregister"},
            project_id="local",
            market=command.market,
        ):
            raise _not_found()
        try:
            return _pipeline_from_paper(
                repository,
                paper_text=command.paper_text,
                market=command.market.value,
                user_prompt=None,
                actor_id=actor.actor_id,
                idempotency_key=idempotency_key,
                request_payload=command.model_dump(mode="json"),
                horizon=command.horizon,
                random_seed=command.random_seed,
                snapshot_id=command.snapshot_id,
                snapshot_manifest_hash=command.snapshot_manifest_hash,
            )
        except FactorExtractionError as exc:
            raise ProblemError(
                status=422,
                code="FACTOR_EXTRACTION_FAILED",
                title="Factor extraction failed",
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise _problem(exc) from exc

    @router.post("/research-pipelines:from-paper-file", status_code=202)
    async def create_research_from_paper_file(
        file: UploadFile = File(...),  # noqa: B008
        prompt: str = Form(""),
        market: str = Form(...),
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
    ) -> dict[str, Any]:
        if not actor.can(
            {"research.jobs.manage", "research.experiments.preregister"},
            project_id="local",
            market=market,
        ):
            raise _not_found()
        try:
            content = await file.read()
            paper_text = parse_attachment(file.filename or "upload", content)
            payload = {
                "prompt": prompt,
                "market": market,
                "filename": file.filename,
            }
            return _pipeline_from_paper(
                repository,
                paper_text=paper_text,
                market=market,
                user_prompt=prompt or None,
                actor_id=actor.actor_id,
                idempotency_key=idempotency_key,
                request_payload=payload,
                horizon="5 trading days",
                random_seed=42,
                snapshot_id=None,
                snapshot_manifest_hash=None,
            )
        except FactorExtractionError as exc:
            raise ProblemError(
                status=422,
                code="FACTOR_EXTRACTION_FAILED",
                title="Factor extraction failed",
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise _problem(exc) from exc

    @router.post("/experiments:preregister", status_code=202)
    def preregister(
        command: PreregisterExperimentCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
    ) -> dict[str, Any]:
        market = str(command.factor_ir.get("market_scope", {}).get("market", ""))
        if not actor.can(
            {"research.experiments.preregister", "research.jobs.manage"},
            project_id="local",
            market=market,
        ):
            raise _not_found()
        try:
            receipt = repository.preregister(
                actor_id=actor.actor_id,
                project_id="local",
                market=market,
                idempotency_key=idempotency_key,
                request_hash=_request_hash(command.model_dump(mode="json")),
                reason=command.metadata.reason,
                parent_artifact_id=command.metadata.parent_artifact_id,
                research_job_id=command.research_job_id,
                brief_version_id=command.brief_version_id,
                decision_time=command.decision_time,
                random_seed=command.random_seed,
                resource_budget=ResourceBudget(**command.resource_budget.model_dump()),
                factor_ir_payload=command.factor_ir,
                snapshot_id=command.snapshot_id,
                snapshot_manifest_hash=command.snapshot_manifest_hash,
            )
        except ValueError as exc:
            raise _problem(exc) from exc
        return receipt.model_dump(mode="json")

    @router.get("/formal-snapshots")
    def list_formal_snapshots(
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if not actor.scopes(
            {
                "research.experiments.read",
                "research.jobs.read",
                "research.jobs.manage",
            }
        ):
            raise _not_found()
        return {"items": repository.list_formal_snapshots()}

    @router.get("/label-snapshots")
    def list_label_snapshots(
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if not actor.scopes(
            {
                "research.experiments.read",
                "research.jobs.read",
                "research.jobs.manage",
            }
        ):
            raise _not_found()
        return {"items": repository.list_label_snapshots()}

    @router.post("/data-provisioning", status_code=202)
    def provision_data(
        command: ProvisionCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if not actor.can(
            {"research.experiments.preregister", "research.jobs.manage"},
            project_id="local",
            market="CN_COMMODITY_FUTURES",
        ):
            raise _not_found()
        if provisioning is None or task_manager is None:
            raise ProblemError(
                status=503,
                code="DATA_PROVISIONING_UNAVAILABLE",
                title="Data provisioning unavailable",
                detail="Data provisioning is not configured for this deployment.",
            )
        try:
            spec = UniverseResolver().resolve(
                command.universe_ref,
                explicit=tuple(command.explicit_instruments),
                exchange_scope=tuple(command.exchange_scope),
            )
        except ValueError as exc:
            raise ProblemError(
                status=422,
                code="DATA_PROVISIONING_FAILED",
                title="Data provisioning failed",
                detail=str(exc),
            ) from exc

        def work() -> ProvisionResult:
            result = provisioning.provision(spec, start=command.start, end=command.end)
            repository.register_snapshot(result.formal_snapshot, result.label_snapshot)
            return result

        task_id = task_manager.start(work)
        return {"task_id": task_id, "status": "PENDING"}

    @router.get("/data-provisioning/{task_id}")
    def get_provisioning_task(
        task_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if not actor.can(
            {"research.experiments.preregister", "research.jobs.manage"},
            project_id="local",
            market="CN_COMMODITY_FUTURES",
        ):
            raise _not_found()
        if task_manager is None:
            raise ProblemError(
                status=503,
                code="DATA_PROVISIONING_UNAVAILABLE",
                title="Data provisioning unavailable",
                detail="Data provisioning is not configured for this deployment.",
            )
        task = task_manager.get(task_id)
        if task is None:
            raise _not_found()
        result = task.result
        return {
            "task_id": task.task_id,
            "status": task.status,
            "error": task.error,
            "snapshot_id": result.snapshot_id if result else None,
            "snapshot_manifest_hash": (
                result.snapshot_manifest_hash if result else None
            ),
            "decision_time": result.decision_time if result else None,
            "instrument_count": result.instrument_count if result else None,
            "row_count": result.row_count if result else None,
            "label_snapshot_id": (
                str(result.label_snapshot["snapshot_id"]) if result else None
            ),
            "label_snapshot_manifest_hash": (
                result.label_manifest_hash if result else None
            ),
            "instruments": list(result.instruments) if result else None,
        }

    @router.get("/experiments/{experiment_id}")
    def get_experiment(
        experiment_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        record = repository.get_experiment(
            experiment_id,
            scopes=actor.scopes(
                {"research.experiments.read", "research.experiments.run"}
            ),
        )
        if record is None:
            raise _not_found()
        return record

    @router.post("/experiments/{experiment_id}:run", status_code=202)
    def run_experiment(
        experiment_id: str,
        command: RunExperimentCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> dict[str, Any]:
        if if_match is None:
            raise ProblemError(
                status=428,
                code="PRECONDITION_REQUIRED",
                title="Precondition required",
                detail="If-Match is required for experiment execution.",
            )
        try:
            receipt = repository.run(
                actor_id=actor.actor_id,
                scopes=actor.scopes({"research.experiments.run"}),
                experiment_id=experiment_id,
                idempotency_key=idempotency_key,
                request_hash=_request_hash(
                    {
                        "experiment_id": experiment_id,
                        **command.model_dump(mode="json"),
                    }
                ),
                reason=command.metadata.reason,
                parent_artifact_id=command.metadata.parent_artifact_id,
                expected_resource_version=_resource_version(if_match),
            )
        except ValueError as exc:
            raise _problem(exc) from exc
        return receipt.model_dump(mode="json")

    @router.post("/experiment-runs/{run_id}:validate", status_code=202)
    def validate_run(
        run_id: str,
        command: ValidateExperimentCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
    ) -> dict[str, Any]:
        try:
            receipt = repository.validate(
                actor_id=actor.actor_id,
                scopes=actor.scopes({"research.experiments.run"}),
                run_id=run_id,
                idempotency_key=idempotency_key,
                request_hash=_request_hash(
                    {"run_id": run_id, **command.model_dump(mode="json")}
                ),
                reason=command.metadata.reason,
                parent_artifact_id=command.metadata.parent_artifact_id,
                policy_id=command.policy_id,
                label_snapshot_id=command.label_snapshot_id,
                label_snapshot_manifest_hash=command.label_snapshot_manifest_hash,
            )
        except ValueError as exc:
            raise _problem(exc) from exc
        return receipt.model_dump(mode="json")

    @router.post("/experiment-runs/{run_id}:assess-robustness", status_code=202)
    def assess_robustness(
        run_id: str,
        command: AssessRobustnessCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
    ) -> dict[str, Any]:
        try:
            receipt = repository.assess_robustness(
                actor_id=actor.actor_id,
                scopes=actor.scopes({"research.experiments.run"}),
                run_id=run_id,
                idempotency_key=idempotency_key,
                request_hash=_request_hash(
                    {"run_id": run_id, **command.model_dump(mode="json")}
                ),
                reason=command.metadata.reason,
                parent_artifact_id=command.metadata.parent_artifact_id,
                policy_id=command.policy_id,
                label_snapshot_id=command.label_snapshot_id,
                label_snapshot_manifest_hash=command.label_snapshot_manifest_hash,
                n_shuffles=command.n_shuffles,
                seed=command.seed,
            )
        except ValueError as exc:
            raise _problem(exc) from exc
        return receipt.model_dump(mode="json")

    @router.post("/experiment-runs/{run_id}:assess-independence", status_code=202)
    def assess_independence(
        run_id: str,
        command: AssessIndependenceCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
    ) -> dict[str, Any]:
        try:
            receipt = repository.assess_independence(
                actor_id=actor.actor_id,
                scopes=actor.scopes({"research.experiments.run"}),
                run_id=run_id,
                idempotency_key=idempotency_key,
                request_hash=_request_hash(
                    {"run_id": run_id, **command.model_dump(mode="json")}
                ),
                reason=command.metadata.reason,
                parent_artifact_id=command.metadata.parent_artifact_id,
                policy_id=command.policy_id,
                label_snapshot_id=command.label_snapshot_id,
                label_snapshot_manifest_hash=command.label_snapshot_manifest_hash,
                pool_run_ids=command.pool_run_ids,
            )
        except ValueError as exc:
            raise _problem(exc) from exc
        return receipt.model_dump(mode="json")

    @router.post("/experiment-runs/{run_id}:promote", status_code=202)
    def promote(
        run_id: str,
        command: PromoteCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
    ) -> dict[str, Any]:
        evidence = command.evidence
        try:
            receipt = repository.promote(
                actor_id=actor.actor_id,
                scopes=actor.scopes({"research.experiments.run"}),
                run_id=run_id,
                idempotency_key=idempotency_key,
                request_hash=_request_hash(
                    {"run_id": run_id, **command.model_dump(mode="json")}
                ),
                reason=command.metadata.reason,
                parent_artifact_id=command.metadata.parent_artifact_id,
                policy_id=command.policy_id,
                direction=command.direction,
                universe=command.universe,
                horizon=command.horizon,
                risk_premium=command.risk_premium,
                evidence=CandidateEvidence(
                    coverage=evidence.coverage,
                    observations=evidence.observations,
                    oos_ic=evidence.oos_ic,
                    expected_direction=ICSign(evidence.expected_direction),
                    fdr_qvalue=evidence.fdr_qvalue,
                    capacity_aum=evidence.capacity_aum,
                    sharpe=evidence.sharpe,
                    effect_score=evidence.effect_score,
                    stability_score=evidence.stability_score,
                    independence_score=evidence.independence_score,
                    cost_value_score=evidence.cost_value_score,
                    interpretability_score=evidence.interpretability_score,
                ),
            )
        except ValueError as exc:
            raise _problem(exc) from exc
        return receipt.model_dump(mode="json")

    @router.get("/experiment-runs/{run_id}/validation")
    def get_validation(
        run_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        record = repository.get_validation(
            run_id,
            scopes=actor.scopes(
                {"research.experiments.read", "research.experiments.run"}
            ),
        )
        if record is None:
            raise _not_found()
        return record

    @router.get("/experiment-runs/{run_id}/robustness")
    def get_robustness(
        run_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        record = repository.get_robustness(
            run_id,
            scopes=actor.scopes(
                {"research.experiments.read", "research.experiments.run"}
            ),
        )
        if record is None:
            raise _not_found()
        return record

    @router.get("/experiment-runs/{run_id}/independence")
    def get_independence(
        run_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        record = repository.get_independence(
            run_id,
            scopes=actor.scopes(
                {"research.experiments.read", "research.experiments.run"}
            ),
        )
        if record is None:
            raise _not_found()
        return record

    @router.get("/experiment-runs/{run_id}/promotion")
    def get_promotion(
        run_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        record = repository.get_promotion(
            run_id,
            scopes=actor.scopes(
                {"research.experiments.read", "research.experiments.run"}
            ),
        )
        if record is None:
            raise _not_found()
        return record

    @router.get("/experiment-runs/{run_id}")
    def get_run(
        run_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        record = repository.get_run(
            run_id,
            scopes=actor.scopes(
                {"research.experiments.read", "research.experiments.run"}
            ),
        )
        if record is None:
            raise _not_found()
        return record

    @router.get("/experiment-runs/{run_id}/artifacts")
    def get_artifacts(
        run_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        record = repository.list_artifacts(
            run_id,
            scopes=actor.scopes(
                {"research.experiments.read", "research.experiments.run"}
            ),
        )
        if record is None:
            raise _not_found()
        return record

    @router.get("/approvals/{workflow_id}")
    def get_approval(
        workflow_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        record = repository.get_approval_workflow(workflow_id)
        if record is None:
            raise _not_found()
        return record

    @router.post("/approvals/{workflow_id}:sign", status_code=202)
    def sign_approval(
        workflow_id: str,
        command: SignApprovalCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        scopes = actor.scopes({"research.governance.approve"})
        if not scopes:
            raise _problem(ValueError("INSUFFICIENT_SCOPE"))
        try:
            return repository.sign_approval_workflow(
                workflow_id=workflow_id,
                actor_id=actor.actor_id,
                decision=command.decision,
                reason=command.reason,
            )
        except ValueError as exc:
            raise _problem(exc) from exc

    @router.get("/session")
    def get_session(
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        capabilities = sorted({grant.capability for grant in actor.grants})
        markets = sorted({grant.market for grant in actor.grants})
        return {
            "actor": {"id": actor.actor_id, "displayName": actor.actor_id},
            "roles": ["Researcher"],
            "capabilities": capabilities,
            "environments": ["RESEARCH", "PAPER", "LIVE"],
            "markets": markets,
        }

    @router.get("/alpha-pool")
    def list_alpha_pool(
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        factors = repository.list_alpha_pool(
            scopes=actor.scopes(
                {"research.experiments.read", "research.strategy.read"}
            ),
        )
        return {"items": factors}

    @router.post("/backtests", status_code=200)
    def run_backtest(
        command: RunBacktestCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        try:
            return repository.run_factor_backtest(
                factor_ir_hash=command.factor_ir_hash,
                instrument_ids=(
                    tuple(command.instrument_ids) if command.instrument_ids else None
                ),
                start=command.start_date,
                end=command.end_date,
                frequency=command.frequency,
                data_source=command.data_source,
                lot_size=command.lot_size,
                initial_cash=Decimal(str(command.initial_cash)),
                scopes=actor.scopes(
                    {"research.experiments.read", "research.strategy.read"}
                ),
            )
        except ValueError as exc:
            raise _problem(exc) from exc

    @router.get("/market-data/coverage")
    def market_data_coverage(
        instruments: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        instrument_ids = tuple(
            item.strip() for item in instruments.split(",") if item.strip()
        )
        return repository.market_data_coverage(
            instrument_ids,
            scopes=actor.scopes(
                {"research.experiments.read", "research.strategy.read"}
            ),
        )

    @router.get("/execution/state")
    def get_execution_state(
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        return repository.get_execution_state()

    @router.post("/execution/kill-switch:trip", status_code=202)
    def trip_kill_switch(
        command: SignApprovalCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        scopes = actor.scopes({"research.governance.approve"})
        if not scopes:
            raise _problem(ValueError("INSUFFICIENT_SCOPE"))
        try:
            return repository.trip_kill_switch(
                actor_id=actor.actor_id, reason=command.reason
            )
        except ValueError as exc:
            raise _problem(exc) from exc

    @router.post("/execution/kill-switch:reset", status_code=202)
    def reset_kill_switch(
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        scopes = actor.scopes({"research.governance.approve"})
        if not scopes:
            raise _problem(ValueError("INSUFFICIENT_SCOPE"))
        try:
            return repository.reset_kill_switch(actor_id=actor.actor_id)
        except ValueError as exc:
            raise _problem(exc) from exc

    return router


def _request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _not_found() -> ProblemError:
    return ProblemError(
        status=404,
        code="RESOURCE_NOT_FOUND",
        title="Resource not found",
        detail="The resource does not exist or is not visible to this principal.",
    )


def _problem(exc: ValueError) -> ProblemError:
    code, _, _ = str(exc).partition(":")
    if code == "RESOURCE_NOT_FOUND":
        return _not_found()
    status = {
        "IDEMPOTENCY_KEY_REUSE": 409,
        "RESOURCE_VERSION_MISMATCH": 412,
    }.get(code, 422)
    return ProblemError(
        status=status,
        code=code,
        title="Experiment command rejected",
        detail=str(exc),
    )


def _resource_version(if_match: str) -> int:
    normalized = if_match.strip()
    if len(normalized) < 3 or not (
        normalized.startswith('"') and normalized.endswith('"')
    ):
        raise ProblemError(
            status=400,
            code="INVALID_IF_MATCH",
            title="Invalid If-Match",
            detail='If-Match must be a quoted integer ETag such as "1".',
        )
    try:
        return int(normalized[1:-1])
    except ValueError as exc:
        raise ProblemError(
            status=400,
            code="INVALID_IF_MATCH",
            title="Invalid If-Match",
            detail='If-Match must be a quoted integer ETag such as "1".',
        ) from exc
