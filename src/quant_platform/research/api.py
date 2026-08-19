from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from quant_platform.research.factor_extract import (
    FactorExtractionError,
    extract_factor_from_paper,
)
from quant_platform.research.paper_parse import PaperParseError, parse_paper_to_brief
from quant_platform.research.repository import SqlAlchemyResearchRepository
from quant_platform.research.schemas import (
    CommandMetadata,
    CreateResearchBriefVersionCommand,
    CreateResearchJobCommand,
    ExtractFactorCommand,
    MarketId,
    ParsePaperCommand,
    ResearchBriefRecord,
    ResearchJobRecord,
    ResearchJobState,
    UpdateResearchBriefVersionCommand,
)
from quant_platform.security import (
    AuthenticationError,
    PrincipalProvider,
)


@dataclass(frozen=True)
class ResearchGrant:
    capability: str
    project_id: str
    market: str


@dataclass(frozen=True)
class ResearchPrincipal:
    actor_id: str
    grants: frozenset[ResearchGrant]

    def scopes(self, capabilities: Iterable[str]) -> frozenset[tuple[str, str]]:
        allowed = frozenset(capabilities)
        return frozenset(
            (grant.project_id, grant.market)
            for grant in self.grants
            if grant.capability in allowed
        )

    def can(
        self,
        capabilities: Iterable[str],
        *,
        project_id: str,
        market: str,
    ) -> bool:
        return (project_id, market) in self.scopes(capabilities)


ResearchPrincipalProvider = Callable[[str], ResearchPrincipal | None]


def adapt_security_principal_provider(
    provider: PrincipalProvider,
) -> ResearchPrincipalProvider:
    def resolve(token: str) -> ResearchPrincipal | None:
        try:
            principal = provider.authenticate(f"Bearer {token}")
        except AuthenticationError:
            return None
        grants = frozenset(
            ResearchGrant(
                capability=capability.name,
                project_id=capability.scope.project_id,
                market=capability.scope.market.value,
            )
            for capability in principal.capabilities
        )
        return ResearchPrincipal(actor_id=principal.actor_id, grants=grants)

    return resolve


class ProblemError(Exception):
    def __init__(
        self,
        *,
        status: int,
        code: str,
        title: str,
        detail: str,
        current_version: str | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.current_version = current_version


def problem_response(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    current_version: str | None = None,
    field_errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"https://quant.example/problems/{code.lower().replace('_', '-')}",
            "title": title,
            "status": status,
            "detail": detail,
            "code": code,
            "request_id": f"req_{uuid4().hex}",
            "retryable": False,
            "current_version": current_version,
            "field_errors": field_errors or [],
        },
    )


def install_problem_handlers(application: FastAPI) -> None:
    @application.exception_handler(ProblemError)
    async def handle_problem(_request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(
            status=exc.status,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            current_version=exc.current_version,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors = [
            {
                "path": ".".join(str(part) for part in error["loc"]),
                "code": str(error["type"]),
                "message": str(error["msg"]),
            }
            for error in exc.errors()
        ]
        return problem_response(
            status=422,
            code="VALIDATION_ERROR",
            title="Request validation failed",
            detail="One or more request fields are invalid.",
            field_errors=field_errors,
        )


def build_research_router(
    repository: SqlAlchemyResearchRepository,
    principal_provider: ResearchPrincipalProvider,
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["ResearchJobs"])

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

    @router.get("/research-jobs")
    def list_research_jobs(
        market: MarketId | None = None,
        state: ResearchJobState | None = None,
        cursor: str | None = None,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del cursor
        scopes = actor.scopes({"research.jobs.read", "research.jobs.manage"})
        if market is not None and not any(
            scope_market == market for _, scope_market in scopes
        ):
            return {"items": [], "next_cursor": None}
        records = repository.list_jobs(
            scopes=scopes,
            market=market,
            state=state,
        )
        return {
            "items": [
                _job_snapshot(
                    record,
                    experiment_id=repository.latest_experiment_id(record.id),
                )
                for record in records
            ],
            "next_cursor": None,
        }

    @router.post("/research-jobs", status_code=202)
    def create_research_job(
        command: CreateResearchJobCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
    ) -> dict[str, Any]:
        if not actor.can(
            {"research.jobs.write", "research.jobs.manage"},
            project_id="local",
            market=command.market,
        ):
            raise _not_found()
        payload = command.model_dump(mode="json")
        request_hash = _request_hash(payload)
        try:
            receipt = repository.execute_create_job_command(
                actor_id=actor.actor_id,
                project_id="local",
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                reason=command.metadata.reason,
                parent_artifact_id=command.metadata.parent_artifact_id,
                title=f"{command.market} {command.horizon} research",
                market=command.market,
                environment=command.environment,
                universe_ref=command.universe_ref,
                frequency=command.frequency,
                decision_clock=command.decision_clock,
                trade_clock=command.trade_clock,
                settlement_clock=command.settlement_clock,
                exchange_scope=command.exchange_scope,
                contract_selection=command.contract_selection,
                roll_policy=command.roll_policy,
                horizon=command.horizon,
                research_brief_version_id=command.research_brief_version_id,
                budget=command.metadata.budget.model_dump(mode="json"),
            )
        except ValueError as exc:
            raise _problem_from_value_error(exc) from exc
        return receipt.model_dump(mode="json")

    @router.get("/research-jobs/{job_id}")
    def get_research_job(
        job_id: str,
        response: Response,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        record = repository.get_job(
            job_id,
            scopes=actor.scopes({"research.jobs.read", "research.jobs.manage"}),
        )
        if record is None:
            raise _not_found()
        response.headers["ETag"] = _etag(record.resource_version)
        return _job_snapshot(
            record,
            experiment_id=repository.latest_experiment_id(record.id),
        )

    @router.get("/research-jobs/{job_id}/brief-versions")
    def list_research_brief_versions(
        job_id: str,
        cursor: str | None = None,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del cursor
        _authorized_job(
            repository,
            job_id,
            actor,
            {"research.jobs.read", "research.jobs.manage"},
        )
        return {
            "items": [
                brief.model_dump(mode="json")
                for brief in repository.list_briefs(job_id)
            ],
            "next_cursor": None,
        }

    @router.post("/research-jobs/{job_id}/brief-versions", status_code=202)
    def create_research_brief_version(
        job_id: str,
        command: CreateResearchBriefVersionCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
        if_match: str = Header(alias="If-Match", min_length=3),
    ) -> dict[str, Any]:
        _authorized_job(
            repository,
            job_id,
            actor,
            {"research.briefs.write", "research.jobs.manage"},
        )
        expected_version = _parse_etag(if_match)
        payload = {"job_id": job_id, **command.model_dump(mode="json")}
        try:
            receipt = repository.execute_create_brief_command(
                job_id=job_id,
                actor_id=actor.actor_id,
                idempotency_key=idempotency_key,
                request_hash=_request_hash(payload),
                reason=command.metadata.reason,
                parent_artifact_id=command.metadata.parent_artifact_id,
                content=command.brief,
                expected_job_version=expected_version,
            )
        except ValueError as exc:
            raise _problem_from_value_error(exc) from exc
        return receipt.model_dump(mode="json")

    @router.get("/research-brief-versions/{brief_version_id}")
    def get_research_brief_version(
        brief_version_id: str,
        response: Response,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        brief_record = _authorized_brief(
            repository,
            brief_version_id,
            actor,
            {"research.jobs.read", "research.jobs.manage"},
        )
        response.headers["ETag"] = _etag(brief_record.resource_version)
        return brief_record.model_dump(mode="json")

    @router.patch("/research-brief-versions/{brief_version_id}", status_code=202)
    def update_research_brief_version(
        brief_version_id: str,
        command: UpdateResearchBriefVersionCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
        if_match: str = Header(alias="If-Match", min_length=3),
    ) -> dict[str, Any]:
        _authorized_brief(
            repository,
            brief_version_id,
            actor,
            {"research.briefs.write", "research.jobs.manage"},
        )
        expected_version = _parse_etag(if_match)
        payload = {
            "brief_version_id": brief_version_id,
            **command.model_dump(mode="json"),
        }
        try:
            receipt = repository.execute_update_brief_command(
                brief_id=brief_version_id,
                actor_id=actor.actor_id,
                idempotency_key=idempotency_key,
                request_hash=_request_hash(payload),
                reason=command.metadata.reason,
                parent_artifact_id=command.metadata.parent_artifact_id,
                content=command.brief,
                expected_resource_version=expected_version,
            )
        except ValueError as exc:
            raise _problem_from_value_error(exc) from exc
        return receipt.model_dump(mode="json")

    @router.post("/research-brief-versions/{brief_version_id}:freeze", status_code=202)
    def freeze_research_brief_version(
        brief_version_id: str,
        metadata: CommandMetadata,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
        if_match: str = Header(alias="If-Match", min_length=3),
    ) -> dict[str, Any]:
        _authorized_brief(
            repository,
            brief_version_id,
            actor,
            {"research.briefs.freeze", "research.jobs.manage"},
        )
        expected_version = _parse_etag(if_match)
        payload = {
            "brief_version_id": brief_version_id,
            **metadata.model_dump(mode="json"),
        }
        try:
            receipt = repository.execute_freeze_brief_command(
                brief_id=brief_version_id,
                actor_id=actor.actor_id,
                idempotency_key=idempotency_key,
                request_hash=_request_hash(payload),
                reason=metadata.reason,
                parent_artifact_id=metadata.parent_artifact_id,
                expected_resource_version=expected_version,
            )
        except ValueError as exc:
            raise _problem_from_value_error(exc) from exc
        return receipt.model_dump(mode="json")

    @router.post("/research-briefs:from-paper")
    def parse_paper_brief(
        command: ParsePaperCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if not actor.can(
            {"research.briefs.write", "research.jobs.manage"},
            project_id="local",
            market=command.market,
        ):
            raise _not_found()
        try:
            brief = parse_paper_to_brief(command.paper_text)
        except PaperParseError as exc:
            raise ProblemError(
                status=422,
                code="PAPER_PARSE_FAILED",
                title="Paper parse failed",
                detail=str(exc),
            ) from exc
        return {"brief": brief.model_dump(mode="json")}

    @router.post("/research-briefs:extract-factor")
    def extract_factor(
        command: ExtractFactorCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if not actor.can(
            {"research.briefs.write", "research.jobs.manage"},
            project_id="local",
            market=command.market,
        ):
            raise _not_found()
        try:
            extraction = extract_factor_from_paper(
                command.paper_text, command.market
            )
        except FactorExtractionError as exc:
            raise ProblemError(
                status=422,
                code="FACTOR_EXTRACTION_FAILED",
                title="Factor extraction failed",
                detail=str(exc),
            ) from exc
        return {
            "brief": extraction.brief.model_dump(mode="json"),
            "factor_ir": extraction.factor_ir,
            "explanation": extraction.explanation,
        }

    return router


def _request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _authorized_job(
    repository: SqlAlchemyResearchRepository,
    job_id: str,
    actor: ResearchPrincipal,
    capabilities: set[str],
) -> ResearchJobRecord:
    record = repository.get_job(job_id, scopes=actor.scopes(capabilities))
    if record is None:
        raise _not_found()
    return record


def _authorized_brief(
    repository: SqlAlchemyResearchRepository,
    brief_id: str,
    actor: ResearchPrincipal,
    capabilities: set[str],
) -> ResearchBriefRecord:
    record = repository.get_brief(brief_id)
    if record is None:
        raise _not_found()
    _authorized_job(repository, record.job_id, actor, capabilities)
    return record


def _not_found() -> ProblemError:
    return ProblemError(
        status=404,
        code="RESOURCE_NOT_FOUND",
        title="Resource not found",
        detail="The resource does not exist or is not visible to this principal.",
    )


def _problem_from_value_error(exc: ValueError) -> ProblemError:
    code, _, current_version = str(exc).partition(":")
    if code == "RESOURCE_NOT_FOUND":
        return _not_found()
    titles = {
        "BRIEF_NOT_DRAFT": "Research brief is immutable",
        "STALE_OBJECT_VERSION": "Object version has changed",
        "FREQUENCY_NOT_ENABLED": "Frequency is not enabled",
        "FUTURES_FIELDS_REQUIRED": "Futures fields are required",
        "IDEMPOTENCY_KEY_REUSE": "Idempotency key already used",
    }
    return ProblemError(
        status=(
            409
            if code
            in {
                "BRIEF_NOT_DRAFT",
                "IDEMPOTENCY_KEY_REUSE",
                "STALE_OBJECT_VERSION",
            }
            else 422
        ),
        code=code,
        title=titles.get(code, "Research command rejected"),
        detail=str(exc),
        current_version=current_version or None,
    )


def _format_etag(version: str) -> str:
    if not version.strip() or '"' in version or version.startswith("W/"):
        raise ValueError("ETag version must be a non-empty strong token")
    return f'"{version}"'


def _parse_strong_etag(value: str) -> str:
    if not value or value.startswith("W/") or len(value) < 3:
        raise ValueError("If-Match must contain a strong ETag")
    if not (value.startswith('"') and value.endswith('"')):
        raise ValueError("If-Match must contain a quoted strong ETag")
    version = value[1:-1]
    if not version or '"' in version or "," in version:
        raise ValueError("If-Match must contain one strong ETag")
    return version


def _parse_etag(value: str) -> int:
    try:
        return int(_parse_strong_etag(value))
    except ValueError as exc:
        raise ProblemError(
            status=400,
            code="INVALID_ETAG",
            title="Invalid If-Match header",
            detail="If-Match must contain a strong quoted integer ETag.",
        ) from exc


def _etag(version: int) -> str:
    return _format_etag(str(version))


def _job_snapshot(
    record: ResearchJobRecord,
    *,
    experiment_id: str | None,
) -> dict[str, Any]:
    return {
        "id": record.id,
        "version": str(record.resource_version),
        "title": record.title,
        "market": record.market,
        "environment": record.environment,
        "state": record.state,
        "owner": record.owner,
        "current_stage": "RESEARCH_INTAKE",
        "budget": record.budget,
        "budget_used": {},
        "latest_attempt": None,
        "snapshot_refs": [],
        "policy_version": "validation-policy://pending",
        "run_fingerprint": None,
        "experiment_id": experiment_id,
        "freshness": {
            "as_of": record.updated_at.isoformat(),
            "is_stale": False,
            "stale_reason": None,
        },
        "blockers": [],
        "allowed_actions": ["VIEW", "EDIT_BRIEF", "FREEZE_BRIEF"],
        "updated_at": record.updated_at.isoformat(),
    }
