from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from quant_platform.artifacts import ArtifactStore, canonical_bytes
from quant_platform.data_gateway import (
    ArtifactClass,
    DatasetContract,
    FieldContract,
    FrozenSnapshot,
    InMemorySnapshotStore,
    PITDataGateway,
    PITRow,
    QueryPurpose,
    SnapshotQuery,
    SourceClass,
)
from quant_platform.experiment_runtime.catalog import (
    ExecutionIdentity,
    FormalSnapshotCatalog,
)
from quant_platform.experiments import (
    ArtifactManifest,
    ExperimentSpec,
    FactorComputationArtifact,
    FactorObservation,
    FormalSnapshotBinding,
    InvarianceEvidence,
    LineageEdge,
    LineageRelation,
    ResourceBudget,
    ValidationArtifact,
    ValidationSummary,
    canonical_hash,
    canonical_json,
    compute_run_fingerprint,
    validate_formal_preconditions,
)
from quant_platform.factor_executor import FactorInputRow, FactorTable, execute_factor
from quant_platform.factor_ir import compile_factor_ir
from quant_platform.research.models import (
    AuditEventModel,
    ExperimentArtifactModel,
    ExperimentAttemptModel,
    ExperimentCommandReceiptModel,
    ExperimentLineageModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    FactorValidationModel,
    OutboxEventModel,
)
from quant_platform.research.repository import SqlAlchemyResearchRepository
from quant_platform.research.schemas import CommandReceipt
from quant_platform.validation import (
    ForwardReturnLabel,
    InMemoryValidationPolicyCatalog,
    LabelObservation,
    LabelSeries,
    ValidationPolicyCatalog,
    assert_label_pit_safe,
    validate_factor,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _json_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class SqlAlchemyExperimentRepository:
    def __init__(
        self,
        engine: Engine,
        *,
        research_repository: SqlAlchemyResearchRepository,
        artifact_store: ArtifactStore,
        snapshot_catalog: FormalSnapshotCatalog,
        execution_identity: ExecutionIdentity,
        before_commit: Callable[[], None] | None = None,
        policy_catalog: ValidationPolicyCatalog | None = None,
    ) -> None:
        self._engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)
        self._research = research_repository
        self._artifacts = artifact_store
        self._snapshot_catalog = snapshot_catalog
        self._execution_identity = execution_identity
        self._before_commit = before_commit
        self._policy_catalog = policy_catalog or InMemoryValidationPolicyCatalog(())

    def preregister(
        self,
        *,
        actor_id: str,
        project_id: str,
        market: str,
        idempotency_key: str,
        request_hash: str,
        reason: str,
        parent_artifact_id: str | None,
        research_job_id: str,
        brief_version_id: str,
        decision_time: datetime,
        random_seed: int,
        resource_budget: ResourceBudget,
        factor_ir_payload: dict[str, Any],
        snapshot_id: str,
        snapshot_manifest_hash: str,
    ) -> CommandReceipt:
        job = self._research.get_job(
            research_job_id, scopes=frozenset({(project_id, market)})
        )
        brief = self._research.get_brief(brief_version_id)
        if job is None or brief is None or brief.job_id != research_job_id:
            raise ValueError("RESOURCE_NOT_FOUND")
        compiled = compile_factor_ir(factor_ir_payload)
        snapshot_payload = self._snapshot_catalog.resolve(
            snapshot_id, snapshot_manifest_hash
        )
        snapshot, binding = _snapshot(snapshot_payload)
        brief_hash = (brief.content_hash or "").removeprefix("sha256:")
        spec = ExperimentSpec.draft(
            experiment_id=f"exp_{uuid4().hex}",
            project_id=project_id,
            research_job_id=research_job_id,
            brief_version_id=brief_version_id,
            brief_content_hash=brief_hash,
            factor_ir_hash=compiled.ir_hash,
            snapshot_id=snapshot.snapshot_id,
            snapshot_manifest_hash=snapshot_manifest_hash,
            market=job.market.value,
            universe_ref=job.universe_ref,
            frequency=job.frequency,
            decision_time=decision_time,
            decision_clock=job.decision_clock,
            trade_clock=job.trade_clock,
            settlement_clock=job.settlement_clock,
            exchange_scope=tuple(job.exchange_scope),
            contract_chain_ref=binding.contract_chain_ref,
            roll_policy_ref=binding.roll_policy_ref,
            validation_policy_ref=str(factor_ir_payload["validation_policy_ref"]),
            license_purpose=binding.purpose,
            allowed_license_tags=binding.allowed_license_tags,
            random_seed=random_seed,
            resource_budget=resource_budget,
        ).preregister(actor_id=actor_id, at=_now())
        binding = replace(
            binding,
            snapshot_manifest_hash=spec.snapshot_manifest_hash,
        )
        validate_formal_preconditions(
            spec=spec,
            research_job=job,
            research_brief=brief,
            frozen_snapshot=snapshot,
            snapshot_binding=binding,
            compiled_ir=compiled,
        )
        receipt = CommandReceipt(
            command_id=f"cmd_{uuid4().hex}",
            resource_id=spec.experiment_id,
            submitted_at=_now(),
        )
        with self._sessions.begin() as session:
            self._lock_key(session, actor_id, idempotency_key)
            stored_receipt = session.get(
                ExperimentCommandReceiptModel, (actor_id, idempotency_key)
            )
            if stored_receipt is not None:
                if stored_receipt.request_hash != request_hash:
                    raise ValueError("IDEMPOTENCY_KEY_REUSE")
                return CommandReceipt.model_validate(stored_receipt.response)
            timestamp = _now()
            session.add_all(
                [
                    ExperimentSpecModel(
                        id=spec.experiment_id,
                        project_id=project_id,
                        research_job_id=research_job_id,
                        brief_version_id=brief_version_id,
                        market=market,
                        state=spec.state.value,
                        resource_version=1,
                        spec_hash=spec.spec_hash,
                        factor_ir_hash=spec.factor_ir_hash,
                        snapshot_id=spec.snapshot_id,
                        snapshot_manifest_hash=spec.snapshot_manifest_hash,
                        spec_payload=_spec_payload(spec),
                        factor_ir_payload=factor_ir_payload,
                        snapshot_payload=snapshot_payload,
                        created_at=timestamp,
                        created_by=actor_id,
                    ),
                    ExperimentCommandReceiptModel(
                        actor_id=actor_id,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        response=receipt.model_dump(mode="json"),
                        created_at=timestamp,
                    ),
                    _audit(
                        actor_id,
                        "experiment.preregistered",
                        spec.experiment_id,
                        reason,
                        parent_artifact_id,
                        receipt.command_id,
                        spec.spec_hash,
                    ),
                    _outbox(
                        "ExperimentPreregistered",
                        "ExperimentSpec",
                        spec.experiment_id,
                        receipt.command_id,
                        {"market": market, "spec_hash": spec.spec_hash},
                    ),
                ]
            )
            self._run_before_commit()
        return receipt

    def get_experiment(
        self, experiment_id: str, *, scopes: frozenset[tuple[str, str]]
    ) -> dict[str, Any] | None:
        with self._sessions() as session:
            model = session.get(ExperimentSpecModel, experiment_id)
            if model is None or (model.project_id, model.market) not in scopes:
                return None
            latest_run_id = session.scalar(
                select(ExperimentRunModel.id)
                .where(ExperimentRunModel.experiment_id == experiment_id)
                .order_by(ExperimentRunModel.created_at.desc())
                .limit(1)
            )
            return {
                "id": model.id,
                "project_id": model.project_id,
                "research_job_id": model.research_job_id,
                "brief_version_id": model.brief_version_id,
                "market": model.market,
                "state": model.state,
                "resource_version": model.resource_version,
                "spec_hash": model.spec_hash,
                "factor_ir_hash": model.factor_ir_hash,
                "snapshot_id": model.snapshot_id,
                "snapshot_manifest_hash": model.snapshot_manifest_hash,
                "latest_run_id": latest_run_id,
                "created_at": model.created_at,
                "created_by": model.created_by,
            }

    def run(
        self,
        *,
        actor_id: str,
        scopes: frozenset[tuple[str, str]],
        experiment_id: str,
        idempotency_key: str,
        request_hash: str,
        reason: str,
        parent_artifact_id: str | None,
        expected_resource_version: int,
    ) -> CommandReceipt:
        with self._sessions() as session:
            model = session.get(ExperimentSpecModel, experiment_id)
            if model is None or (model.project_id, model.market) not in scopes:
                raise ValueError("RESOURCE_NOT_FOUND")
            if model.resource_version != expected_resource_version:
                raise ValueError("RESOURCE_VERSION_MISMATCH")
            replay_receipt = self._command_replay(
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            if replay_receipt is not None:
                return replay_receipt
            factor_payload = dict(model.factor_ir_payload)
            snapshot_payload = dict(model.snapshot_payload)
            spec_payload = dict(model.spec_payload)
        compiled = compile_factor_ir(factor_payload)
        snapshot, binding = _snapshot(snapshot_payload)
        spec = _spec(spec_payload)
        job = self._research.get_job(
            spec.research_job_id,
            scopes=frozenset({(model.project_id, model.market)}),
        )
        brief = self._research.get_brief(spec.brief_version_id)
        if job is None or brief is None or brief.job_id != spec.research_job_id:
            raise ValueError("RESOURCE_NOT_FOUND")
        validate_formal_preconditions(
            spec=spec,
            research_job=job,
            research_brief=brief,
            frozen_snapshot=snapshot,
            snapshot_binding=binding,
            compiled_ir=compiled,
        )
        fingerprint = compute_run_fingerprint(
            experiment_spec_hash=spec.spec_hash,
            factor_ir_hash=compiled.ir_hash,
            snapshot_id=spec.snapshot_id,
            snapshot_manifest_hash=spec.snapshot_manifest_hash,
            code_sha=self._execution_identity.code_sha,
            image_digest=self._execution_identity.image_digest,
            dependency_lock_hash=self._execution_identity.dependency_lock_hash,
            executor_version=self._execution_identity.executor_version,
            config_hash=self._execution_identity.config_hash,
            random_seed=spec.random_seed,
        )
        input_table = _factor_table(compiled.canonical_json, snapshot, spec)
        result = execute_factor(compiled, input_table)
        referenced_fields = {
            item["field_ref"] for item in json.loads(compiled.canonical_json)["inputs"]
        }
        # Future-truncation evidence: compare the gateway-filtered result
        # against an explicitly truncated table built without the gateway, so a
        # gateway regression that leaks future rows surfaces as a mismatch.
        future_truncated_snapshot = FrozenSnapshot.create(
            snapshot_id=snapshot.snapshot_id,
            frozen_at=snapshot.frozen_at,
            contracts=tuple(snapshot.contracts.values()),
            rows=tuple(
                row for row in snapshot.rows if row.available_time <= spec.decision_time
            ),
            artifact_class=snapshot.artifact_class,
        )
        future_comparison = execute_factor(
            compiled,
            _factor_table_direct(compiled.canonical_json, future_truncated_snapshot),
        )
        # Sentinel-isolation evidence: the IR must not reference any sentinel
        # field injected into the formal snapshot. This is a direct, falsifiable
        # field check rather than a vacuous hash comparison.
        sentinel_fields = {
            row.field for row in snapshot.rows if "sentinel" in row.field.lower()
        }
        sentinel_isolation_passed = not (referenced_fields & sentinel_fields)
        sentinel_isolated_snapshot = FrozenSnapshot.create(
            snapshot_id=snapshot.snapshot_id,
            frozen_at=snapshot.frozen_at,
            contracts=tuple(snapshot.contracts.values()),
            rows=tuple(row for row in snapshot.rows if row.field in referenced_fields),
            artifact_class=snapshot.artifact_class,
        )
        sentinel_comparison = execute_factor(
            compiled,
            _factor_table(compiled.canonical_json, sentinel_isolated_snapshot, spec),
        )
        run_id = f"run_{uuid4().hex}"
        attempt_id = f"attempt_{uuid4().hex}"
        observations = tuple(
            FactorObservation(item.instrument_id, item.timestamp, item.value)
            for item in result.observations
        )
        computation = FactorComputationArtifact.create(
            artifact_id=f"artifact_{uuid4().hex}",
            run_id=run_id,
            attempt_id=attempt_id,
            experiment_spec_hash=spec.spec_hash,
            factor_ir_hash=compiled.ir_hash,
            snapshot_id=spec.snapshot_id,
            snapshot_manifest_hash=spec.snapshot_manifest_hash,
            input_hash=canonical_hash(input_table),
            observations=observations,
        )
        finite = [item.value for item in observations if item.value is not None]
        summary = ValidationSummary(
            observation_count=len(observations),
            finite_count=len(finite),
            missing_count=len(observations) - len(finite),
            coverage_ratio=len(finite) / len(observations) if observations else 0.0,
            minimum=min(finite) if finite else None,
            maximum=max(finite) if finite else None,
            mean=sum(finite) / len(finite) if finite else None,
        )
        invariance = InvarianceEvidence(
            future_truncation_passed=(
                result.output_hash == future_comparison.output_hash
            ),
            sentinel_isolation_passed=sentinel_isolation_passed,
            baseline_output_hash=result.output_hash,
            future_truncation_output_hash=future_comparison.output_hash,
            sentinel_isolation_output_hash=sentinel_comparison.output_hash,
        )
        validation = ValidationArtifact.create(
            artifact_id=f"artifact_{uuid4().hex}",
            run_id=run_id,
            attempt_id=attempt_id,
            experiment_spec_hash=spec.spec_hash,
            computation_artifact_hash=computation.manifest.content_hash,
            summary=summary,
            invariance=invariance,
            input_hash=computation.manifest.content_hash,
            output_hash=canonical_hash({"summary": summary, "invariance": invariance}),
        )
        computation_bytes = canonical_bytes(computation.payload())
        validation_bytes = canonical_bytes(validation.payload())
        computation_store = self._artifacts.put(
            computation_bytes, media_type="application/json"
        )
        validation_store = self._artifacts.put(
            validation_bytes, media_type="application/json"
        )
        edge = LineageEdge(
            computation_store.content_hash,
            validation_store.content_hash,
            LineageRelation.VALIDATED_BY,
        )
        receipt = CommandReceipt(
            command_id=f"cmd_{uuid4().hex}",
            resource_id=run_id,
            submitted_at=_now(),
        )
        with self._sessions.begin() as session:
            self._lock_key(session, actor_id, idempotency_key)
            stored_receipt = session.get(
                ExperimentCommandReceiptModel, (actor_id, idempotency_key)
            )
            if stored_receipt is not None:
                if stored_receipt.request_hash != request_hash:
                    raise ValueError("IDEMPOTENCY_KEY_REUSE")
                return CommandReceipt.model_validate(stored_receipt.response)
            self._lock_fingerprint(session, fingerprint)
            existing = session.scalar(
                select(ExperimentRunModel).where(
                    ExperimentRunModel.run_fingerprint == fingerprint
                )
            )
            if existing is not None:
                replay = CommandReceipt(
                    command_id=receipt.command_id,
                    resource_id=existing.id,
                    submitted_at=receipt.submitted_at,
                )
                session.add_all(
                    [
                        ExperimentCommandReceiptModel(
                            actor_id=actor_id,
                            idempotency_key=idempotency_key,
                            request_hash=request_hash,
                            response=replay.model_dump(mode="json"),
                            created_at=_now(),
                        ),
                        _audit(
                            actor_id,
                            "experiment.run.reused",
                            existing.id,
                            reason,
                            parent_artifact_id,
                            replay.command_id,
                            fingerprint,
                        ),
                        _outbox(
                            "ExperimentRunReused",
                            "ExperimentRun",
                            existing.id,
                            replay.command_id,
                            {
                                "experiment_id": experiment_id,
                                "fingerprint": fingerprint,
                            },
                        ),
                    ]
                )
                self._run_before_commit()
                return replay
            timestamp = _now()
            session.add(
                ExperimentRunModel(
                    id=run_id,
                    experiment_id=experiment_id,
                    project_id=model.project_id,
                    market=model.market,
                    state="SUCCEEDED",
                    run_fingerprint=fingerprint,
                    attempt_count=1,
                    validation_summary=_json(summary),
                    invariance=_json(invariance),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            session.flush()
            session.add(
                ExperimentAttemptModel(
                    id=attempt_id,
                    run_id=run_id,
                    ordinal=1,
                    state="SUCCEEDED",
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            session.flush()
            session.add_all(
                [
                    _artifact_model(
                        computation_store,
                        run_id,
                        attempt_id,
                        "FactorComputationArtifact",
                        "factor-computation/v1",
                        computation.manifest.content_hash,
                        timestamp,
                    ),
                    _artifact_model(
                        validation_store,
                        run_id,
                        attempt_id,
                        "ValidationArtifact",
                        "factor-validation/v1",
                        validation.manifest.content_hash,
                        timestamp,
                    ),
                    ExperimentLineageModel(
                        edge_hash=edge.edge_hash,
                        run_id=run_id,
                        source_artifact_hash=edge.source_artifact_hash,
                        target_artifact_hash=edge.target_artifact_hash,
                        relation=edge.relation.value,
                    ),
                    ExperimentCommandReceiptModel(
                        actor_id=actor_id,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        response=receipt.model_dump(mode="json"),
                        created_at=timestamp,
                    ),
                    _audit(
                        actor_id,
                        "experiment.run.succeeded",
                        run_id,
                        reason,
                        parent_artifact_id,
                        receipt.command_id,
                        validation.manifest.content_hash,
                    ),
                    _outbox(
                        "ExperimentRunSucceeded",
                        "ExperimentRun",
                        run_id,
                        receipt.command_id,
                        {"experiment_id": experiment_id, "fingerprint": fingerprint},
                    ),
                ]
            )
            self._run_before_commit()
        return receipt

    def _command_replay(
        self,
        *,
        actor_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> CommandReceipt | None:
        with self._sessions() as session:
            existing = session.get(
                ExperimentCommandReceiptModel, (actor_id, idempotency_key)
            )
            if existing is None:
                return None
            if existing.request_hash != request_hash:
                raise ValueError("IDEMPOTENCY_KEY_REUSE")
            return CommandReceipt.model_validate(existing.response)

    def validate(
        self,
        *,
        actor_id: str,
        scopes: frozenset[tuple[str, str]],
        run_id: str,
        idempotency_key: str,
        request_hash: str,
        reason: str,
        parent_artifact_id: str | None,
        policy_id: str,
        label_payload: dict[str, Any],
        label_available_time: datetime,
    ) -> CommandReceipt:
        policy = self._policy_catalog.resolve(policy_id)
        label = _label_series(label_payload)

        with self._sessions.begin() as session:
            self._lock_key(session, actor_id, idempotency_key)
            stored_receipt = session.get(
                ExperimentCommandReceiptModel, (actor_id, idempotency_key)
            )
            if stored_receipt is not None:
                if stored_receipt.request_hash != request_hash:
                    raise ValueError("IDEMPOTENCY_KEY_REUSE")
                return CommandReceipt.model_validate(stored_receipt.response)

            run = session.get(ExperimentRunModel, run_id)
            if run is None or (run.project_id, run.market) not in scopes:
                raise ValueError("RESOURCE_NOT_FOUND")
            if run.state != "SUCCEEDED":
                raise ValueError("RUN_NOT_SUCCEEDED")

            factor, factor_store_address = self._load_factor_artifact(session, run_id)
            decision_time = self._decision_time(session, run.experiment_id)
            assert_label_pit_safe(
                label_available_time=label_available_time,
                decision_time=decision_time,
            )

            report = validate_factor(factor, label, policy)

            validation_id = f"validation_{uuid4().hex}"
            report_store = self._artifacts.put(
                canonical_bytes(report.payload()), media_type="application/json"
            )
            edge = LineageEdge(
                source_artifact_hash=factor_store_address,
                target_artifact_hash=report_store.content_hash,
                relation=LineageRelation.VALIDATED_BY,
            )
            receipt = CommandReceipt(
                command_id=f"cmd_{uuid4().hex}",
                resource_id=validation_id,
                submitted_at=_now(),
            )
            timestamp = _now()
            session.add_all(
                [
                    FactorValidationModel(
                        id=validation_id,
                        run_id=run_id,
                        policy_id=policy.policy_id,
                        policy_hash=policy.content_hash(),
                        label_id=label.label.label_id,
                        label_hash=label.content_hash(),
                        factor_artifact_hash=factor_store_address,
                        output_hash=report.output_hash,
                        report_payload=report.payload(),
                        created_at=timestamp,
                    ),
                    ExperimentLineageModel(
                        edge_hash=edge.edge_hash,
                        run_id=run_id,
                        source_artifact_hash=edge.source_artifact_hash,
                        target_artifact_hash=edge.target_artifact_hash,
                        relation=edge.relation.value,
                    ),
                    ExperimentCommandReceiptModel(
                        actor_id=actor_id,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        response=receipt.model_dump(mode="json"),
                        created_at=timestamp,
                    ),
                    _audit(
                        actor_id,
                        "experiment.validate.succeeded",
                        run_id,
                        reason,
                        parent_artifact_id,
                        receipt.command_id,
                        report.output_hash,
                    ),
                    _outbox(
                        "ExperimentValidated",
                        "ExperimentRun",
                        run_id,
                        receipt.command_id,
                        {"run_id": run_id, "output_hash": report.output_hash},
                    ),
                ]
            )
            self._run_before_commit()
        return receipt

    def _load_factor_artifact(
        self, session: Session, run_id: str
    ) -> tuple[FactorComputationArtifact, str]:
        model = session.scalar(
            select(ExperimentArtifactModel).where(
                ExperimentArtifactModel.run_id == run_id,
                ExperimentArtifactModel.artifact_type == "FactorComputationArtifact",
            )
        )
        if model is None:
            raise ValueError("FACTOR_ARTIFACT_NOT_FOUND")
        payload = json.loads(self._artifacts.get(model.content_hash).decode())
        manifest = ArtifactManifest(
            artifact_id=model.id,
            artifact_type=model.artifact_type,
            schema_version=model.schema_version,
            content_hash=model.domain_hash,
        )
        factor = FactorComputationArtifact.from_payload(
            payload,
            artifact_id=model.id,
            run_id=model.run_id,
            attempt_id=model.attempt_id,
            manifest=manifest,
        )
        return factor, model.content_hash

    def _decision_time(self, session: Session, experiment_id: str) -> datetime:
        spec = session.get(ExperimentSpecModel, experiment_id)
        if spec is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        value = spec.spec_payload.get("decision_time")
        if not isinstance(value, str):
            raise ValueError("SPEC_DECISION_TIME_MISSING")
        return datetime.fromisoformat(value)

    def get_run(
        self, run_id: str, *, scopes: frozenset[tuple[str, str]]
    ) -> dict[str, Any] | None:
        with self._sessions() as session:
            model = session.get(ExperimentRunModel, run_id)
            if model is None or (model.project_id, model.market) not in scopes:
                return None
            return {
                "id": model.id,
                "experiment_id": model.experiment_id,
                "market": model.market,
                "state": model.state,
                "run_fingerprint": model.run_fingerprint,
                "attempt_count": model.attempt_count,
                "validation_summary": model.validation_summary,
                "invariance": model.invariance,
                "created_at": model.created_at,
                "updated_at": model.updated_at,
            }

    def list_artifacts(
        self, run_id: str, *, scopes: frozenset[tuple[str, str]]
    ) -> dict[str, Any] | None:
        if self.get_run(run_id, scopes=scopes) is None:
            return None
        with self._sessions() as session:
            artifacts = session.scalars(
                select(ExperimentArtifactModel).where(
                    ExperimentArtifactModel.run_id == run_id
                )
            ).all()
            lineage = session.scalars(
                select(ExperimentLineageModel).where(
                    ExperimentLineageModel.run_id == run_id
                )
            ).all()
            return {
                "items": [
                    {
                        "content_hash": item.content_hash,
                        "artifact_type": item.artifact_type,
                        "schema_version": item.schema_version,
                        "size_bytes": item.size_bytes,
                        "media_type": item.media_type,
                        "domain_hash": item.domain_hash,
                    }
                    for item in artifacts
                ],
                "lineage": [
                    {
                        "edge_hash": item.edge_hash,
                        "source_artifact_hash": item.source_artifact_hash,
                        "target_artifact_hash": item.target_artifact_hash,
                        "relation": item.relation,
                    }
                    for item in lineage
                ],
            }

    def _lock_key(self, session: Session, actor_id: str, key: str) -> None:
        if self._engine.dialect.name == "postgresql":
            self._advisory_lock(session, f"idempotency:{actor_id}:{key}")

    def _lock_fingerprint(self, session: Session, fingerprint: str) -> None:
        if self._engine.dialect.name == "postgresql":
            self._advisory_lock(session, f"run-fingerprint:{fingerprint}")

    @staticmethod
    def _advisory_lock(session: Session, value: str) -> None:
        digest = hashlib.sha256(value.encode()).digest()
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": int.from_bytes(digest[:8], "big", signed=True)},
        )

    def _run_before_commit(self) -> None:
        if self._before_commit is not None:
            self._before_commit()


def _snapshot(payload: dict[str, Any]) -> tuple[FrozenSnapshot, FormalSnapshotBinding]:
    contracts = tuple(
        DatasetContract(
            dataset_id=item["dataset_id"],
            source_id=item["source_id"],
            source_class=SourceClass(item["source_class"]),
            fields=tuple(
                FieldContract(
                    name=field["name"],
                    value_type=field["value_type"],
                    unit=field["unit"],
                    license_tag=field["license_tag"],
                    allowed_purposes=frozenset(
                        QueryPurpose(value) for value in field["allowed_purposes"]
                    ),
                )
                for field in item["fields"]
            ),
        )
        for item in payload["datasets"]
    )
    rows = tuple(
        PITRow(
            dataset_id=item["dataset_id"],
            field=item["field"],
            instrument_id=item["instrument_id"],
            event_time=datetime.fromisoformat(item["event_time"]),
            available_time=datetime.fromisoformat(item["available_time"]),
            ingested_at=datetime.fromisoformat(item["ingested_at"]),
            revision_id=item["revision_id"],
            source_id=item["source_id"],
            license_tag=item["license_tag"],
            value=item["value"],
        )
        for item in payload["rows"]
    )
    artifact_class = ArtifactClass(payload["artifact_class"])
    snapshot = FrozenSnapshot.create(
        snapshot_id=payload["snapshot_id"],
        frozen_at=datetime.fromisoformat(payload["frozen_at"]),
        contracts=contracts,
        rows=rows,
        artifact_class=artifact_class,
    )
    return snapshot, FormalSnapshotBinding(
        snapshot_id=snapshot.snapshot_id,
        snapshot_manifest_hash=canonical_hash(payload),
        sealed=bool(payload["sealed"]),
        artifact_class=artifact_class,
        market=payload["market"],
        universe_ref=payload["universe_ref"],
        frequency=payload["frequency"],
        decision_clock=payload["decision_clock"],
        trade_clock=payload["trade_clock"],
        settlement_clock=payload.get("settlement_clock"),
        exchange_scope=tuple(payload.get("exchange_scope", [])),
        contract_chain_ref=payload.get("contract_chain_ref"),
        roll_policy_ref=payload.get("roll_policy_ref"),
        purpose=QueryPurpose(payload["purpose"]),
        allowed_license_tags=frozenset(payload["allowed_license_tags"]),
    )


def _factor_table(
    canonical_ir: str, snapshot: FrozenSnapshot, spec: ExperimentSpec
) -> FactorTable:
    document = json.loads(canonical_ir)
    gateway = PITDataGateway(InMemorySnapshotStore((snapshot,)))
    values: dict[tuple[datetime, str], dict[str, float | None]] = defaultdict(dict)
    for input_item in document["inputs"]:
        field = input_item["field_ref"]
        for contract in snapshot.contracts.values():
            if field not in {item.name for item in contract.fields}:
                continue
            result = gateway.query(
                SnapshotQuery(
                    snapshot_id=snapshot.snapshot_id,
                    dataset_id=contract.dataset_id,
                    fields=(field,),
                    decision_time=spec.decision_time,
                    purpose=QueryPurpose.RESEARCH,
                    allowed_license_tags=spec.allowed_license_tags,
                )
            )
            for row in result.rows:
                value = row.value
                values[(row.event_time, row.instrument_id)][input_item["alias"]] = (
                    float(value)
                    if isinstance(value, int | float)
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    else None
                )
    return FactorTable(
        tuple(
            FactorInputRow(timestamp, instrument, row_values)
            for (timestamp, instrument), row_values in values.items()
        )
    )


def _factor_table_direct(canonical_ir: str, snapshot: FrozenSnapshot) -> FactorTable:
    """Build a factor table directly from snapshot rows, bypassing the PIT
    gateway's available-time filter.

    This is used only for invariance-evidence comparison: it feeds an
    already-truncated snapshot so a gateway regression that leaks future rows
    would surface as a hash mismatch against the authoritative result. It must
    never feed a real computation.
    """
    document = json.loads(canonical_ir)
    aliases = {item["field_ref"]: item["alias"] for item in document["inputs"]}
    values: dict[tuple[datetime, str], dict[str, float | None]] = defaultdict(dict)
    for row in snapshot.rows:
        alias = aliases.get(row.field)
        if alias is None:
            continue
        value = row.value
        values[(row.event_time, row.instrument_id)][alias] = (
            float(value)
            if isinstance(value, int | float)
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            else None
        )
    return FactorTable(
        tuple(
            FactorInputRow(timestamp, instrument, row_values)
            for (timestamp, instrument), row_values in values.items()
        )
    )


def _spec_payload(spec: ExperimentSpec) -> dict[str, Any]:
    value = json.loads(
        canonical_json(
            {
                **spec.identity_payload(),
                "state": spec.state.value,
                "spec_hash": spec.spec_hash,
                "preregistered_by": spec.preregistered_by,
                "preregistered_at": spec.preregistered_at,
            }
        )
    )
    if not isinstance(value, dict):
        raise TypeError("ExperimentSpec payload must serialize to an object")
    return value


def _spec(payload: dict[str, Any]) -> ExperimentSpec:
    stored_spec_hash = str(payload["spec_hash"])
    budget = ResourceBudget(**payload.pop("resource_budget"))
    payload["decision_time"] = datetime.fromisoformat(payload["decision_time"])
    payload["exchange_scope"] = tuple(payload["exchange_scope"])
    payload["allowed_license_tags"] = frozenset(payload["allowed_license_tags"])
    payload["resource_budget"] = budget
    payload.pop("state", None)
    payload.pop("spec_hash", None)
    payload.pop("preregistered_by", None)
    payload.pop("preregistered_at", None)
    spec = ExperimentSpec.draft(**payload).preregister(actor_id="stored", at=_now())
    if spec.spec_hash != stored_spec_hash:
        raise ValueError("STORED_SPEC_HASH_MISMATCH")
    return spec


def _json(value: ValidationSummary | InvarianceEvidence) -> dict[str, Any]:
    result = json.loads(canonical_json(value))
    if not isinstance(result, dict):
        raise TypeError("domain summary must serialize to an object")
    return result


def _artifact_model(
    manifest: Any,
    run_id: str,
    attempt_id: str,
    artifact_type: str,
    schema_version: str,
    domain_hash: str,
    timestamp: datetime,
) -> ExperimentArtifactModel:
    return ExperimentArtifactModel(
        id=f"artifact_meta_{uuid4().hex}",
        content_hash=manifest.content_hash,
        run_id=run_id,
        attempt_id=attempt_id,
        artifact_type=artifact_type,
        schema_version=schema_version,
        size_bytes=manifest.size_bytes,
        media_type=manifest.media_type,
        domain_hash=domain_hash,
        created_at=timestamp,
    )


def _audit(
    actor: str,
    action: str,
    resource_id: str,
    reason: str,
    parent_artifact_id: str | None,
    command_id: str,
    after_hash: str,
) -> AuditEventModel:
    return AuditEventModel(
        id=f"audit_{uuid4().hex}",
        occurred_at=_now(),
        actor=actor,
        action=action,
        resource_id=resource_id,
        resource_version="1",
        reason=reason,
        parent_artifact_id=parent_artifact_id,
        request_id=command_id,
        correlation_id=command_id,
        policy_decision="RESEARCH_ONLY",
        before_hash=None,
        after_hash=after_hash,
    )


def _outbox(
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    command_id: str,
    payload: dict[str, Any],
) -> OutboxEventModel:
    return OutboxEventModel(
        event_id=f"evt_{uuid4().hex}",
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version="1",
        occurred_at=_now(),
        payload={"command_id": command_id, **payload},
        schema_version="v1",
        sequence=None,
        published=False,
        published_at=None,
    )


def _label_series(payload: dict[str, Any]) -> LabelSeries:
    label = ForwardReturnLabel(
        label_id=str(payload["label_id"]),
        market=str(payload["market"]),
        horizon=int(payload["horizon"]),
        field_ref=str(payload["field_ref"]),
        return_definition=str(payload.get("return_definition", "close_to_close")),
    )
    observations = tuple(
        LabelObservation(
            instrument_id=str(item["instrument_id"]),
            event_time=datetime.fromisoformat(item["event_time"]),
            value=item["value"],
        )
        for item in payload["observations"]
    )
    return LabelSeries(label=label, observations=observations)
