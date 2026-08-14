from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ResearchJobModel(Base):
    __tablename__ = "research_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default="local", index=True
    )
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    universe_ref: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    decision_clock: Mapped[str] = mapped_column(String(128), nullable=False)
    trade_clock: Mapped[str] = mapped_column(String(128), nullable=False)
    settlement_clock: Mapped[str | None] = mapped_column(String(128))
    exchange_scope: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    contract_selection: Mapped[str | None] = mapped_column(String(64))
    roll_policy: Mapped[str | None] = mapped_column(Text)
    horizon: Mapped[str] = mapped_column(String(64), nullable=False)
    research_brief_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ResearchBriefVersionModel(Base):
    __tablename__ = "research_brief_versions"
    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_brief_job_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    economic_mechanism: Mapped[str] = mapped_column(Text, nullable=False)
    expected_direction: Mapped[str] = mapped_column(String(32), nullable=False)
    falsification_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    allowed_data_domains: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    forbidden_data_domains: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    constraints: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ref_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    uncertainties: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    frozen_by: Mapped[str | None] = mapped_column(String(255))


class ResearchCommandReceiptModel(Base):
    __tablename__ = "research_command_receipts"

    actor_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_version: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    parent_artifact_id: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    policy_decision: Mapped[str | None] = mapped_column(String(128))
    before_hash: Mapped[str | None] = mapped_column(String(80))
    after_hash: Mapped[str | None] = mapped_column(String(80))


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    aggregate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    sequence: Mapped[int | None] = mapped_column(Integer)
    published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsumerReceiptModel(Base):
    __tablename__ = "consumer_receipts"

    consumer_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"

    namespace: Mapped[str] = mapped_column(String(128), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    response: Mapped[Any] = mapped_column(JSON, nullable=False)
    stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExperimentSpecModel(Base):
    __tablename__ = "experiment_specs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    research_job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brief_version_id: Mapped[str] = mapped_column(
        ForeignKey("research_brief_versions.id"), nullable=False
    )
    market: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    spec_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    factor_ir_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    spec_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    factor_ir_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    snapshot_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class ExperimentRunModel(Base):
    __tablename__ = "experiment_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_specs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    run_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    invariance: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ExperimentAttemptModel(Base):
    __tablename__ = "experiment_attempts"
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_experiment_attempt_ordinal"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ExperimentArtifactModel(Base):
    __tablename__ = "experiment_artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_attempts.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    domain_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ExperimentLineageModel(Base):
    __tablename__ = "experiment_lineage"

    edge_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_artifact_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    target_artifact_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    relation: Mapped[str] = mapped_column(String(64), nullable=False)


class ExperimentCommandReceiptModel(Base):
    __tablename__ = "experiment_command_receipts"

    actor_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class FactorValidationModel(Base):
    __tablename__ = "factor_validations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label_id: Mapped[str] = mapped_column(String(255), nullable=False)
    label_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    factor_artifact_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    report_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class TrialLedgerModel(Base):
    __tablename__ = "trial_ledgers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    factor_ir_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False)
    decision_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AlphaPoolFactorModel(Base):
    __tablename__ = "alpha_pool_factors"

    factor_ir_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    universe: Mapped[str] = mapped_column(String(255), nullable=False)
    horizon: Mapped[int] = mapped_column(Integer(), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_premium: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False)
    oos_ic: Mapped[float | None] = mapped_column(Float(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class IndependenceReportModel(Base):
    __tablename__ = "independence_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    baseline_ic: Mapped[float | None] = mapped_column(Float(), nullable=True)
    orthogonalized_ic: Mapped[float | None] = mapped_column(Float(), nullable=True)
    max_abs_correlation: Mapped[float | None] = mapped_column(Float(), nullable=True)
    replicated_risk_factor: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    report_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PromotionRecordModel(Base):
    __tablename__ = "promotion_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    factor_ir_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    total_score: Mapped[float | None] = mapped_column(Float(), nullable=True)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    report_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class CombinationPoolFactorModel(Base):
    __tablename__ = "combination_pool_factors"

    factor_ir_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    promotion_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    promoted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ApprovalWorkflowModel(Base):
    __tablename__ = "approval_workflows"

    workflow_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False)
    decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
