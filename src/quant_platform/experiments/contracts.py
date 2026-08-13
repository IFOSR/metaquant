from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _canonical_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical datetime must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, set | frozenset):
        normalized = [_canonical_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ),
        )
    if isinstance(value, tuple | list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical numbers must be finite")
        return 0.0 if value == 0 else value
    if value is None or isinstance(value, str | int | bool):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _required(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a normalized non-empty value")


def _hash(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hash")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    cpu_seconds: int
    wall_clock_seconds: int
    memory_mb: int
    max_observations: int

    def __post_init__(self) -> None:
        if (
            min(
                self.cpu_seconds,
                self.wall_clock_seconds,
                self.memory_mb,
                self.max_observations,
            )
            <= 0
        ):
            raise ValueError("resource budget values must be positive")


class ExperimentSpecState(str, Enum):
    DRAFT = "DRAFT"
    PREREGISTERED = "PREREGISTERED"
    SUPERSEDED = "SUPERSEDED"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    experiment_id: str
    project_id: str
    research_job_id: str
    brief_version_id: str
    brief_content_hash: str
    factor_ir_hash: str
    snapshot_id: str
    snapshot_manifest_hash: str
    market: str
    universe_ref: str
    frequency: str
    decision_time: datetime
    decision_clock: str
    trade_clock: str
    settlement_clock: str | None
    exchange_scope: tuple[str, ...]
    contract_chain_ref: str | None
    roll_policy_ref: str | None
    validation_policy_ref: str
    license_purpose: object
    allowed_license_tags: frozenset[str]
    random_seed: int
    resource_budget: ResourceBudget
    state: ExperimentSpecState
    spec_hash: str
    preregistered_by: str | None = None
    preregistered_at: datetime | None = None
    closed_by: str | None = None
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in (
            "experiment_id",
            "project_id",
            "research_job_id",
            "brief_version_id",
            "snapshot_id",
            "market",
            "universe_ref",
            "decision_clock",
            "trade_clock",
            "validation_policy_ref",
        ):
            _required(str(getattr(self, name)), name)
        if "latest" in self.snapshot_id.lower():
            raise ValueError("snapshot_id cannot use latest")
        if self.frequency != "1d":
            raise ValueError("formal ExperimentSpec frequency must be 1d")
        _aware(self.decision_time, "decision_time")
        _hash(self.brief_content_hash, "brief_content_hash")
        _hash(self.factor_ir_hash, "factor_ir_hash")
        _hash(self.snapshot_manifest_hash, "snapshot_manifest_hash")
        _hash(self.spec_hash, "spec_hash")
        if not self.allowed_license_tags:
            raise ValueError("allowed_license_tags must not be empty")
        if self.market == "CN_COMMODITY_FUTURES":
            missing = [
                name
                for name, value in (
                    ("settlement_clock", self.settlement_clock),
                    ("exchange_scope", self.exchange_scope),
                    ("contract_chain_ref", self.contract_chain_ref),
                    ("roll_policy_ref", self.roll_policy_ref),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "commodity futures require " + ", ".join(sorted(missing))
                )
        if self.spec_hash != canonical_hash(self.identity_payload()):
            raise ValueError("spec_hash does not match ExperimentSpec identity")

    @classmethod
    def draft(cls, **values: Any) -> ExperimentSpec:
        identity = dict(values)
        return cls(
            **values,
            state=ExperimentSpecState.DRAFT,
            spec_hash=canonical_hash(identity),
        )

    def identity_payload(self) -> dict[str, object]:
        excluded = {
            "state",
            "spec_hash",
            "preregistered_by",
            "preregistered_at",
            "closed_by",
            "closed_at",
        }
        return {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if item.name not in excluded
        }

    def revise(self, **changes: Any) -> ExperimentSpec:
        if self.state is not ExperimentSpecState.DRAFT:
            raise ValueError("preregistered ExperimentSpec is immutable")
        identity = self.identity_payload()
        identity.update(changes)
        return ExperimentSpec.draft(**identity)

    def preregister(self, *, actor_id: str, at: datetime) -> ExperimentSpec:
        if self.state is not ExperimentSpecState.DRAFT:
            raise ValueError("only a draft ExperimentSpec can be preregistered")
        _required(actor_id, "actor_id")
        _aware(at, "preregistered_at")
        return replace(
            self,
            state=ExperimentSpecState.PREREGISTERED,
            preregistered_by=actor_id,
            preregistered_at=at,
        )

    def close(self, *, actor_id: str, at: datetime) -> ExperimentSpec:
        if self.state is not ExperimentSpecState.PREREGISTERED:
            raise ValueError("only a preregistered ExperimentSpec can be closed")
        _required(actor_id, "actor_id")
        _aware(at, "closed_at")
        return replace(
            self,
            state=ExperimentSpecState.CLOSED,
            closed_by=actor_id,
            closed_at=at,
        )


class ExperimentRunState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    WAITING_INPUT = "WAITING_INPUT"
    BLOCKED_POLICY = "BLOCKED_POLICY"
    QUARANTINED = "QUARANTINED"
    NON_REPRODUCIBLE = "NON_REPRODUCIBLE"
    CANCELLED = "CANCELLED"


_RUN_TRANSITIONS: dict[ExperimentRunState, frozenset[ExperimentRunState]] = {
    ExperimentRunState.QUEUED: frozenset(
        {ExperimentRunState.RUNNING, ExperimentRunState.CANCELLED}
    ),
    ExperimentRunState.RUNNING: frozenset(
        {
            ExperimentRunState.SUCCEEDED,
            ExperimentRunState.FAILED_RETRYABLE,
            ExperimentRunState.FAILED_TERMINAL,
            ExperimentRunState.WAITING_INPUT,
            ExperimentRunState.BLOCKED_POLICY,
            ExperimentRunState.QUARANTINED,
            ExperimentRunState.NON_REPRODUCIBLE,
            ExperimentRunState.CANCELLED,
        }
    ),
    ExperimentRunState.FAILED_RETRYABLE: frozenset(
        {ExperimentRunState.RUNNING, ExperimentRunState.CANCELLED}
    ),
}


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    run_id: str
    experiment_id: str
    experiment_spec_hash: str
    run_fingerprint: str
    state: ExperimentRunState
    queued_at: datetime
    updated_at: datetime
    attempt_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _hash(self.experiment_spec_hash, "experiment_spec_hash")
        _hash(self.run_fingerprint, "run_fingerprint")
        _aware(self.queued_at, "queued_at")
        _aware(self.updated_at, "updated_at")
        if len(set(self.attempt_ids)) != len(self.attempt_ids):
            raise ValueError("attempt_ids must be unique")

    @classmethod
    def queued(
        cls,
        *,
        run_id: str,
        experiment_id: str,
        experiment_spec_hash: str,
        run_fingerprint: str,
        queued_at: datetime,
    ) -> ExperimentRun:
        return cls(
            run_id=run_id,
            experiment_id=experiment_id,
            experiment_spec_hash=experiment_spec_hash,
            run_fingerprint=run_fingerprint,
            state=ExperimentRunState.QUEUED,
            queued_at=queued_at,
            updated_at=queued_at,
        )

    def add_attempt(self, attempt: Attempt) -> ExperimentRun:
        if attempt.run_id != self.run_id:
            raise ValueError("attempt belongs to another run")
        if attempt.attempt_id in self.attempt_ids:
            raise ValueError("attempt history cannot be overwritten")
        if attempt.ordinal != len(self.attempt_ids) + 1:
            raise ValueError("attempt ordinal must append to history")
        return replace(self, attempt_ids=(*self.attempt_ids, attempt.attempt_id))

    def transition(self, state: ExperimentRunState, *, at: datetime) -> ExperimentRun:
        if state not in _RUN_TRANSITIONS.get(self.state, frozenset()):
            raise ValueError(
                f"invalid run transition {self.state.value}->{state.value}"
            )
        _aware(at, "updated_at")
        return replace(self, state=state, updated_at=at)


class AttemptState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


_ATTEMPT_TRANSITIONS: dict[AttemptState, frozenset[AttemptState]] = {
    AttemptState.QUEUED: frozenset({AttemptState.RUNNING, AttemptState.CANCELLED}),
    AttemptState.RUNNING: frozenset(
        {
            AttemptState.SUCCEEDED,
            AttemptState.FAILED,
            AttemptState.CANCELLED,
            AttemptState.TIMED_OUT,
        }
    ),
}


@dataclass(frozen=True, slots=True)
class Attempt:
    attempt_id: str
    run_id: str
    ordinal: int
    state: AttemptState
    queued_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _required(self.attempt_id, "attempt_id")
        _required(self.run_id, "run_id")
        if self.ordinal < 1:
            raise ValueError("attempt ordinal must be positive")
        _aware(self.queued_at, "queued_at")
        _aware(self.updated_at, "updated_at")

    @classmethod
    def queued(
        cls,
        *,
        attempt_id: str,
        run_id: str,
        ordinal: int,
        queued_at: datetime,
    ) -> Attempt:
        if ordinal < 1:
            raise ValueError("attempt ordinal must be positive")
        _aware(queued_at, "queued_at")
        return cls(
            attempt_id=attempt_id,
            run_id=run_id,
            ordinal=ordinal,
            state=AttemptState.QUEUED,
            queued_at=queued_at,
            updated_at=queued_at,
        )

    def transition(self, state: AttemptState, *, at: datetime) -> Attempt:
        if state not in _ATTEMPT_TRANSITIONS.get(self.state, frozenset()):
            raise ValueError(
                f"invalid attempt transition {self.state.value}->{state.value}"
            )
        _aware(at, "updated_at")
        return replace(self, state=state, updated_at=at)


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    artifact_id: str
    artifact_type: str
    schema_version: str
    content_hash: str

    def __post_init__(self) -> None:
        _hash(self.content_hash, "manifest content_hash")


@dataclass(frozen=True, slots=True)
class FactorObservation:
    instrument_id: str
    event_time: datetime
    value: float | None

    def __post_init__(self) -> None:
        _aware(self.event_time, "event_time")
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("factor observation must be finite or null")


@dataclass(frozen=True, slots=True)
class FactorComputationArtifact:
    artifact_id: str
    run_id: str
    attempt_id: str
    experiment_spec_hash: str
    factor_ir_hash: str
    snapshot_id: str
    snapshot_manifest_hash: str
    input_hash: str
    observations: tuple[FactorObservation, ...]
    output_hash: str
    manifest: ArtifactManifest

    def __post_init__(self) -> None:
        if self.output_hash != canonical_hash(self.observations):
            raise ValueError("output_hash does not match observations")
        if self.manifest.content_hash != canonical_hash(self.payload()):
            raise ValueError("manifest does not match computation payload")

    @classmethod
    def create(cls, **values: Any) -> FactorComputationArtifact:
        observations = tuple(values.pop("observations"))
        output_hash = canonical_hash(observations)
        payload = {
            key: value
            for key, value in values.items()
            if key not in {"artifact_id", "run_id", "attempt_id"}
        }
        payload.update({"observations": observations, "output_hash": output_hash})
        manifest = ArtifactManifest(
            artifact_id=values["artifact_id"],
            artifact_type="FactorComputationArtifact",
            schema_version="factor-computation/v1",
            content_hash=canonical_hash(payload),
        )
        return cls(
            **values,
            observations=observations,
            output_hash=output_hash,
            manifest=manifest,
        )

    def payload(self) -> dict[str, object]:
        return {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if item.name not in {"artifact_id", "run_id", "attempt_id", "manifest"}
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        artifact_id: str,
        run_id: str,
        attempt_id: str,
        manifest: ArtifactManifest,
    ) -> FactorComputationArtifact:
        observations = tuple(
            FactorObservation(
                instrument_id=str(item["instrument_id"]),
                event_time=datetime.fromisoformat(item["event_time"]),
                value=item["value"],
            )
            for item in payload["observations"]
        )
        return cls(
            artifact_id=artifact_id,
            run_id=run_id,
            attempt_id=attempt_id,
            experiment_spec_hash=str(payload["experiment_spec_hash"]),
            factor_ir_hash=str(payload["factor_ir_hash"]),
            snapshot_id=str(payload["snapshot_id"]),
            snapshot_manifest_hash=str(payload["snapshot_manifest_hash"]),
            input_hash=str(payload["input_hash"]),
            observations=observations,
            output_hash=str(payload["output_hash"]),
            manifest=manifest,
        )


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    observation_count: int
    finite_count: int
    missing_count: int
    coverage_ratio: float
    minimum: float | None
    maximum: float | None
    mean: float | None

    def __post_init__(self) -> None:
        if (
            self.observation_count < 0
            or self.finite_count < 0
            or self.missing_count < 0
        ):
            raise ValueError("validation counts must be non-negative")
        if self.finite_count + self.missing_count != self.observation_count:
            raise ValueError("validation counts must sum to observation_count")
        expected = (
            self.finite_count / self.observation_count
            if self.observation_count
            else 0.0
        )
        if not math.isclose(self.coverage_ratio, expected):
            raise ValueError("coverage_ratio does not match counts")


@dataclass(frozen=True, slots=True)
class InvarianceEvidence:
    future_truncation_passed: bool
    sentinel_isolation_passed: bool
    baseline_output_hash: str
    future_truncation_output_hash: str
    sentinel_isolation_output_hash: str


@dataclass(frozen=True, slots=True)
class ValidationArtifact:
    artifact_id: str
    run_id: str
    attempt_id: str
    experiment_spec_hash: str
    computation_artifact_hash: str
    summary: ValidationSummary
    invariance: InvarianceEvidence
    input_hash: str
    output_hash: str
    manifest: ArtifactManifest

    def __post_init__(self) -> None:
        if self.manifest.content_hash != canonical_hash(self.payload()):
            raise ValueError("manifest does not match validation payload")

    @classmethod
    def create(cls, **values: Any) -> ValidationArtifact:
        payload = {
            key: value
            for key, value in values.items()
            if key not in {"artifact_id", "run_id", "attempt_id"}
        }
        manifest = ArtifactManifest(
            artifact_id=values["artifact_id"],
            artifact_type="ValidationArtifact",
            schema_version="factor-validation/v1",
            content_hash=canonical_hash(payload),
        )
        return cls(**values, manifest=manifest)

    def payload(self) -> dict[str, object]:
        return {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if item.name not in {"artifact_id", "run_id", "attempt_id", "manifest"}
        }


class LineageRelation(str, Enum):
    DERIVED_FROM = "DERIVED_FROM"
    VALIDATED_BY = "VALIDATED_BY"


@dataclass(frozen=True, slots=True)
class LineageEdge:
    source_artifact_hash: str
    target_artifact_hash: str
    relation: LineageRelation
    edge_hash: str = ""

    def __post_init__(self) -> None:
        expected = canonical_hash(
            {
                "source_artifact_hash": self.source_artifact_hash,
                "target_artifact_hash": self.target_artifact_hash,
                "relation": self.relation,
            }
        )
        if self.edge_hash and self.edge_hash != expected:
            raise ValueError("edge_hash does not match lineage edge")
        object.__setattr__(self, "edge_hash", expected)


def compute_run_fingerprint(**values: object) -> str:
    required = {
        "experiment_spec_hash",
        "factor_ir_hash",
        "snapshot_id",
        "snapshot_manifest_hash",
        "code_sha",
        "image_digest",
        "dependency_lock_hash",
        "executor_version",
        "config_hash",
        "random_seed",
    }
    if set(values) != required:
        missing = sorted(required - values.keys())
        extra = sorted(values.keys() - required)
        raise ValueError(f"invalid fingerprint fields missing={missing} extra={extra}")
    return canonical_hash(values)
