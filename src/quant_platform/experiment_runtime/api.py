from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, Header

from quant_platform.experiment_runtime.repository import (
    SqlAlchemyExperimentRepository,
)
from quant_platform.experiment_runtime.schemas import (
    AssessRobustnessCommand,
    PreregisterExperimentCommand,
    RunExperimentCommand,
    ValidateExperimentCommand,
)
from quant_platform.experiments import ResourceBudget
from quant_platform.research.api import (
    ProblemError,
    ResearchPrincipal,
    ResearchPrincipalProvider,
)


def build_experiment_router(
    repository: SqlAlchemyExperimentRepository,
    principal_provider: ResearchPrincipalProvider,
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
