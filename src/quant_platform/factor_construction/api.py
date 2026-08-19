"""HTTP surface for the factor construction control plane.

Endpoints split into agent drafts (no persistence, mirroring
``research-briefs:from-paper``) and command endpoints (persist + freeze).  The
freeze discipline is enforced server-side: bundles may only be registered
against a frozen spec.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Response

from quant_platform.factor_construction.artifacts import CodeBundleError, bundle_hash
from quant_platform.factor_construction.generator import (
    extract_build_spec,
    generate_and_smoke,
    generate_code_bundle,
)
from quant_platform.factor_construction.repository import (
    SqlAlchemyFactorConstructionRepository,
)
from quant_platform.factor_construction.schemas import (
    CreateFactorBuildSpecCommand,
    ExtractBuildSpecCommand,
    FreezeFactorBuildSpecCommand,
    GenerateCodeBundleCommand,
    GenerateCodeDraftCommand,
    InferFactorCommand,
    TrainFactorCommand,
    ValidateFactorCommand,
)
from quant_platform.factor_construction.service import FactorBuildService
from quant_platform.factor_construction.spec import build_spec_hash
from quant_platform.research.api import (
    ProblemError,
    ResearchPrincipal,
    ResearchPrincipalProvider,
)
from quant_platform.research.factor_extract import FactorExtractionError

_SPEC_CAPS = {"factor_construction.specs.write", "factor_construction.specs.freeze"}
_BUNDLE_CAPS = {"factor_construction.bundles.generate"}


def build_factor_construction_router(
    repository: SqlAlchemyFactorConstructionRepository,
    principal_provider: ResearchPrincipalProvider,
    service: FactorBuildService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["FactorConstruction"])

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

    @router.post("/factor-build-specs:extract")
    def extract_spec(
        command: ExtractBuildSpecCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        try:
            spec = extract_build_spec(
                command.paper_text,
                user_prompt=command.user_prompt,
            )
        except FactorExtractionError as exc:
            raise _agent_failed(exc) from exc
        return {
            "spec": spec.model_dump(mode="json"),
            "spec_hash": build_spec_hash(spec),
        }

    @router.post("/factor-build-specs:generate")
    def generate_spec_draft(
        command: GenerateCodeDraftCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        try:
            files, manifest = generate_code_bundle(command.spec)
        except (FactorExtractionError, CodeBundleError) as exc:
            raise _agent_failed(exc) from exc
        return {
            "files": {
                name: manifest["files"][name]["sha256"] for name in sorted(files)
            },
            "manifest": manifest,
            "bundle_hash": bundle_hash(manifest),
        }

    @router.post("/factor-build-specs:smoke")
    def smoke_spec_draft(
        command: GenerateCodeDraftCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        try:
            files, manifest, result = generate_and_smoke(command.spec)
        except (FactorExtractionError, CodeBundleError) as exc:
            raise _agent_failed(exc) from exc
        return {
            "files": {
                name: manifest["files"][name]["sha256"] for name in sorted(files)
            },
            "manifest": manifest,
            "bundle_hash": bundle_hash(manifest),
            "smoke": {
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "stderr": result.stderr,
            },
        }

    @router.post("/factor-build-specs", status_code=202)
    def create_spec(
        command: CreateFactorBuildSpecCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=16),
    ) -> dict[str, Any]:
        del idempotency_key
        _require_caps(actor, _SPEC_CAPS, command.spec.market)
        try:
            record = repository.create_spec(actor_id=actor.actor_id, spec=command.spec)
        except ValueError as exc:
            raise _problem_from_value_error(exc) from exc
        return record.model_dump(mode="json")

    @router.post("/factor-build-specs/{spec_id}:freeze", status_code=202)
    def freeze_spec(
        spec_id: str,
        command: FreezeFactorBuildSpecCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
        if_match: str = Header(alias="If-Match", min_length=3),
    ) -> dict[str, Any]:
        del command
        existing = repository.get_spec(spec_id)
        if existing is None:
            raise _not_found()
        _require_caps(actor, _SPEC_CAPS, existing.spec.market)
        expected_version = _parse_etag(if_match)
        try:
            record = repository.freeze_spec(
                spec_id=spec_id,
                actor_id=actor.actor_id,
                expected_resource_version=expected_version,
            )
        except ValueError as exc:
            raise _problem_from_value_error(exc) from exc
        return record.model_dump(mode="json")

    @router.post("/factor-build-specs/{spec_id}:generate", status_code=202)
    def generate_spec_bundle(
        spec_id: str,
        command: GenerateCodeBundleCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        existing = repository.get_spec(spec_id)
        if existing is None:
            raise _not_found()
        _require_caps(actor, _BUNDLE_CAPS, existing.spec.market)
        if existing.spec_hash != command.spec_hash:
            raise ProblemError(
                status=409,
                code="SPEC_HASH_MISMATCH",
                title="Spec hash mismatch",
                detail="The spec_hash does not match the frozen spec.",
            )
        if bundle_hash(command.manifest) != command.bundle_hash:
            raise ProblemError(
                status=422,
                code="BUNDLE_HASH_MISMATCH",
                title="Bundle hash mismatch",
                detail="The bundle_hash does not match the supplied manifest.",
            )
        svc = _require_service(service)
        try:
            record = svc.register_bundle(
                actor_id=actor.actor_id,
                spec_hash=existing.spec_hash,
                bundle_hash=command.bundle_hash,
                manifest=command.manifest,
                files_text=command.files,
            )
        except ValueError as exc:
            raise _problem_from_value_error(exc) from exc
        return record.model_dump(mode="json")

    @router.get("/factor-build-specs/{spec_id}")
    def get_spec(
        spec_id: str,
        response: Response,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        record = repository.get_spec(spec_id)
        if record is None:
            raise _not_found()
        response.headers["ETag"] = f'"{record.resource_version}"'
        return record.model_dump(mode="json")

    @router.get("/factor-code-bundles/{bundle_hash}")
    def get_bundle(
        bundle_hash: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        record = repository.get_bundle(bundle_hash)
        if record is None:
            raise _not_found()
        return record.model_dump(mode="json")

    @router.post("/factor-build-specs:train", status_code=202)
    def train_factor(
        command: TrainFactorCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        svc = _require_service(service)
        _require_caps(
            actor,
            {"factor_construction.train"},
            _market(repository, command.spec_hash),
        )
        result = svc.train(
            spec_hash=command.spec_hash,
            bundle_hash=command.bundle_hash,
            instrument_ids=command.instrument_ids,
            decision_time=command.decision_time.isoformat(),
            field_prefix=command.field_prefix,
        )
        return {
            "run": result.run.model_dump(mode="json"),
            "weights_hash": result.weights_hash,
        }

    @router.post("/factor-build-specs:infer", status_code=202)
    def infer_factor(
        command: InferFactorCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        svc = _require_service(service)
        _require_caps(
            actor,
            {"factor_construction.train"},
            _market(repository, command.spec_hash),
        )
        result = svc.infer(
            spec_hash=command.spec_hash,
            bundle_hash=command.bundle_hash,
            weights_hash=command.weights_hash,
            instrument_ids=command.instrument_ids,
            decision_time=command.decision_time.isoformat(),
            field_prefix=command.field_prefix,
        )
        return {
            "run": result.run.model_dump(mode="json"),
            "factor_values_hash": result.factor_values_hash,
            "output_hash": result.output_hash,
            "observation_count": len(result.observations),
        }

    @router.post("/factor-build-specs:validate")
    def validate_factor(
        command: ValidateFactorCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        svc = _require_service(service)
        _require_caps(
            actor,
            {"factor_construction.train"},
            _market(repository, command.spec_hash),
        )
        report = svc.validate(
            factor_values_hash=command.factor_values_hash,
            instrument_ids=command.instrument_ids,
            price_field=command.price_field,
            horizon=command.horizon,
            decision_time=command.decision_time.isoformat(),
            field_prefix=command.field_prefix,
            return_type=command.return_type,
        )
        return report.payload()

    @router.get("/factor-build-runs/{run_id}")
    def get_run(
        run_id: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        record = repository.get_run(run_id)
        if record is None:
            raise _not_found()
        return record.model_dump(mode="json")

    return router


def _agent_failed(exc: Exception) -> ProblemError:
    return ProblemError(
        status=422,
        code="AGENT_GENERATION_FAILED",
        title="Agent generation failed",
        detail=str(exc),
    )


def _require_service(service: FactorBuildService | None) -> FactorBuildService:
    if service is None:
        raise ProblemError(
            status=503,
            code="SERVICE_UNAVAILABLE",
            title="Factor build service unavailable",
            detail="The factor build execution service is not configured.",
        )
    return service


def _market(repository: SqlAlchemyFactorConstructionRepository, spec_hash: str) -> str:
    record = repository.get_spec_by_hash(spec_hash)
    if record is None:
        raise _not_found()
    return record.spec.market


def _require_caps(
    actor: ResearchPrincipal, capabilities: set[str], market: str
) -> None:
    if not actor.can(capabilities, project_id="local", market=market):
        raise _not_found()


def _not_found() -> ProblemError:
    return ProblemError(
        status=404,
        code="RESOURCE_NOT_FOUND",
        title="Resource not found",
        detail="The resource does not exist or is not visible to this principal.",
    )


def _problem_from_value_error(exc: ValueError) -> ProblemError:
    code, _, current_version = str(exc).partition(":")
    titles = {
        "SPEC_ALREADY_EXISTS": "Factor build spec already exists",
        "SPEC_NOT_DRAFT": "Factor build spec is frozen",
        "SPEC_NOT_FROZEN": "Factor build spec is not frozen",
        "BUNDLE_ALREADY_EXISTS": "Code bundle already exists",
        "BUNDLE_SPEC_MISMATCH": "Code bundle spec mismatch",
        "STALE_OBJECT_VERSION": "Object version has changed",
    }
    return ProblemError(
        status=409 if code in {"STALE_OBJECT_VERSION", "SPEC_ALREADY_EXISTS"} else 422,
        code=code,
        title=titles.get(code, "Factor construction command rejected"),
        detail=str(exc),
        current_version=current_version or None,
    )


def _parse_etag(value: str) -> int:
    try:
        if (
            len(value) < 3
            or value.startswith("W/")
            or not (value.startswith('"') and value.endswith('"'))
        ):
            raise ValueError
        return int(value[1:-1])
    except ValueError as exc:
        raise ProblemError(
            status=400,
            code="INVALID_ETAG",
            title="Invalid If-Match header",
            detail="If-Match must contain a strong quoted integer ETag.",
        ) from exc
