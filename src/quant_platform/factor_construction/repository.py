"""SQLAlchemy repository for factor build specs and code bundles.

The freeze discipline lives here: a spec is DRAFT until frozen; once frozen it
is immutable, and a code bundle may only be registered against a frozen spec.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from quant_platform.artifacts.store import ArtifactStore
from quant_platform.factor_construction.schemas import (
    FactorBuildRunKind,
    FactorBuildRunRecord,
    FactorBuildRunState,
    FactorBuildSpecRecord,
    FactorBuildSpecState,
    FactorCodeBundleRecord,
)
from quant_platform.factor_construction.spec import FactorBuildSpec, build_spec_hash
from quant_platform.research.models import (
    AuditEventModel,
    FactorBuildRunModel,
    FactorBuildSpecModel,
    FactorCodeBundleModel,
)


def _now() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyFactorConstructionRepository:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create_spec(
        self,
        *,
        actor_id: str,
        spec: FactorBuildSpec,
        project_id: str = "local",
        research_job_id: str | None = None,
        brief_version_id: str | None = None,
    ) -> FactorBuildSpecRecord:
        spec_hash = build_spec_hash(spec)
        timestamp = _now()
        with self._sessions.begin() as session:
            if self._spec_by_hash(session, spec_hash) is not None:
                raise ValueError("SPEC_ALREADY_EXISTS")
            model = FactorBuildSpecModel(
                id=f"fbs_{uuid4().hex}",
                project_id=project_id,
                research_job_id=research_job_id,
                brief_version_id=brief_version_id,
                spec_hash=spec_hash,
                spec_payload=spec.model_dump(mode="json"),
                state=FactorBuildSpecState.DRAFT,
                resource_version=1,
                created_at=timestamp,
                created_by=actor_id,
                frozen_at=None,
                frozen_by=None,
            )
            session.add(model)
        return self._spec_record(model)

    def freeze_spec(
        self,
        *,
        spec_id: str,
        actor_id: str,
        expected_resource_version: int,
    ) -> FactorBuildSpecRecord:
        with self._sessions.begin() as session:
            model = session.scalar(
                select(FactorBuildSpecModel)
                .where(FactorBuildSpecModel.id == spec_id)
                .with_for_update()
            )
            if model is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            if model.resource_version != expected_resource_version:
                raise ValueError(f"STALE_OBJECT_VERSION:{model.resource_version}")
            if model.state != FactorBuildSpecState.DRAFT:
                raise ValueError("SPEC_NOT_DRAFT")
            model.state = FactorBuildSpecState.FROZEN
            model.resource_version += 1
            model.frozen_at = _now()
            model.frozen_by = actor_id
            session.add(
                AuditEventModel(
                    id=f"audit_{uuid4().hex}",
                    occurred_at=model.frozen_at,
                    actor=actor_id,
                    action="factor_build_spec.frozen",
                    resource_id=model.id,
                    resource_version=str(model.resource_version),
                    reason="freeze factor build spec",
                    parent_artifact_id=None,
                    request_id=None,
                    correlation_id=None,
                    policy_decision="RESEARCH_ONLY",
                    before_hash=None,
                    after_hash=model.spec_hash,
                )
            )
        return self._spec_record(model)

    def create_bundle(
        self,
        *,
        actor_id: str,
        spec_hash: str,
        bundle_hash: str,
        manifest: dict[str, Any],
        files: dict[str, bytes] | None = None,
        artifact_store: ArtifactStore | None = None,
    ) -> FactorCodeBundleRecord:
        if files is not None and artifact_store is not None:
            for payload in files.values():
                artifact_store.put(payload, media_type="text/x-python")
        with self._sessions.begin() as session:
            spec = self._spec_by_hash(session, spec_hash)
            if spec is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            if spec.state != FactorBuildSpecState.FROZEN:
                raise ValueError("SPEC_NOT_FROZEN")
            if self._bundle_by_hash(session, bundle_hash) is not None:
                raise ValueError("BUNDLE_ALREADY_EXISTS")
            if manifest.get("spec_hash") != spec_hash:
                raise ValueError("BUNDLE_SPEC_MISMATCH")
            model = FactorCodeBundleModel(
                id=f"fcb_{uuid4().hex}",
                spec_hash=spec_hash,
                bundle_hash=bundle_hash,
                manifest_payload=dict(manifest),
                created_at=_now(),
                created_by=actor_id,
            )
            session.add(model)
        return self._bundle_record(model)

    def get_bundle_files(
        self, bundle_hash: str, artifact_store: ArtifactStore
    ) -> dict[str, bytes]:
        bundle = self.get_bundle(bundle_hash)
        if bundle is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        files: dict[str, bytes] = {}
        for name, entry in bundle.manifest["files"].items():
            files[name] = artifact_store.get(entry["sha256"])
        return files

    def record_run(
        self,
        *,
        spec_hash: str,
        bundle_hash: str,
        kind: FactorBuildRunKind,
    ) -> FactorBuildRunRecord:
        timestamp = _now()
        model = FactorBuildRunModel(
            id=f"fbr_{uuid4().hex}",
            spec_hash=spec_hash,
            bundle_hash=bundle_hash,
            kind=kind.value,
            state=FactorBuildRunState.QUEUED,
            run_fingerprint=None,
            weights_hash=None,
            factor_values_hash=None,
            error=None,
            logs_ref=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._sessions.begin() as session:
            session.add(model)
        return self._run_record(model)

    def mark_run_running(self, run_id: str) -> FactorBuildRunRecord:
        with self._sessions.begin() as session:
            model = session.scalar(
                select(FactorBuildRunModel)
                .where(FactorBuildRunModel.id == run_id)
                .with_for_update()
            )
            if model is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            model.state = FactorBuildRunState.RUNNING
            model.updated_at = _now()
        return self._run_record(model)

    def complete_run(
        self,
        run_id: str,
        *,
        weights_hash: str | None = None,
        factor_values_hash: str | None = None,
    ) -> FactorBuildRunRecord:
        with self._sessions.begin() as session:
            model = session.scalar(
                select(FactorBuildRunModel)
                .where(FactorBuildRunModel.id == run_id)
                .with_for_update()
            )
            if model is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            model.state = FactorBuildRunState.SUCCEEDED
            model.weights_hash = weights_hash
            model.factor_values_hash = factor_values_hash
            model.updated_at = _now()
        return self._run_record(model)

    def fail_run(self, run_id: str, error: str) -> FactorBuildRunRecord:
        with self._sessions.begin() as session:
            model = session.scalar(
                select(FactorBuildRunModel)
                .where(FactorBuildRunModel.id == run_id)
                .with_for_update()
            )
            if model is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            model.state = FactorBuildRunState.FAILED
            model.error = error
            model.updated_at = _now()
        return self._run_record(model)

    def get_run(self, run_id: str) -> FactorBuildRunRecord | None:
        with self._sessions() as session:
            model = session.get(FactorBuildRunModel, run_id)
            return self._run_record(model) if model is not None else None

    def get_spec(self, spec_id: str) -> FactorBuildSpecRecord | None:
        with self._sessions() as session:
            model = session.get(FactorBuildSpecModel, spec_id)
            return self._spec_record(model) if model is not None else None

    def get_spec_by_hash(self, spec_hash: str) -> FactorBuildSpecRecord | None:
        with self._sessions() as session:
            model = self._spec_by_hash(session, spec_hash)
            return self._spec_record(model) if model is not None else None

    def get_bundle(self, bundle_hash: str) -> FactorCodeBundleRecord | None:
        with self._sessions() as session:
            model = session.scalar(
                select(FactorCodeBundleModel).where(
                    FactorCodeBundleModel.bundle_hash == bundle_hash
                )
            )
            return self._bundle_record(model) if model is not None else None

    @staticmethod
    def _spec_by_hash(session: Session, spec_hash: str) -> FactorBuildSpecModel | None:
        return session.scalar(
            select(FactorBuildSpecModel).where(
                FactorBuildSpecModel.spec_hash == spec_hash
            )
        )

    @staticmethod
    def _spec_record(model: FactorBuildSpecModel) -> FactorBuildSpecRecord:
        return FactorBuildSpecRecord(
            id=model.id,
            project_id=model.project_id,
            research_job_id=model.research_job_id,
            brief_version_id=model.brief_version_id,
            spec_hash=model.spec_hash,
            spec=FactorBuildSpec.model_validate(model.spec_payload),
            state=FactorBuildSpecState(model.state),
            resource_version=model.resource_version,
            created_at=model.created_at,
            created_by=model.created_by,
            frozen_at=model.frozen_at,
            frozen_by=model.frozen_by,
        )

    @staticmethod
    def _bundle_by_hash(
        session: Session, bundle_hash: str
    ) -> FactorCodeBundleModel | None:
        return session.scalar(
            select(FactorCodeBundleModel).where(
                FactorCodeBundleModel.bundle_hash == bundle_hash
            )
        )

    @staticmethod
    def _bundle_record(model: FactorCodeBundleModel) -> FactorCodeBundleRecord:
        return FactorCodeBundleRecord(
            id=model.id,
            spec_hash=model.spec_hash,
            bundle_hash=model.bundle_hash,
            manifest=model.manifest_payload,
            created_at=model.created_at,
            created_by=model.created_by,
        )

    @staticmethod
    def _run_record(model: FactorBuildRunModel) -> FactorBuildRunRecord:
        return FactorBuildRunRecord(
            id=model.id,
            spec_hash=model.spec_hash,
            bundle_hash=model.bundle_hash,
            kind=FactorBuildRunKind(model.kind),
            state=FactorBuildRunState(model.state),
            run_fingerprint=model.run_fingerprint,
            weights_hash=model.weights_hash,
            factor_values_hash=model.factor_values_hash,
            error=model.error,
            logs_ref=model.logs_ref,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
