"""Stable control-plane API, audit, and event contracts."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FieldError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class Problem(BaseModel):
    """RFC 9457 problem details with stable platform extensions."""

    model_config = ConfigDict(extra="forbid")

    type: str = "about:blank"
    title: str = Field(min_length=1)
    status: int = Field(ge=400, le=599)
    detail: str | None = None
    code: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    retryable: bool
    current_version: str | None = None
    field_errors: tuple[FieldError, ...] = ()

    @property
    def media_type(self) -> Literal["application/problem+json"]:
        return "application/problem+json"


class ProblemError(Exception):
    """Exception carrying a serializable Problem response."""

    def __init__(self, problem: Problem) -> None:
        super().__init__(problem.detail or problem.title)
        self.problem = problem


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    occurred_at: datetime
    actor: str = Field(min_length=1)
    action: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    resource_version: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    parent_artifact_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    policy_decision: str | None = None
    before_hash: str | None = None
    after_hash: str | None = None


class OutboxEnvelope(BaseModel):
    """Transactional event payload emitted with an aggregate mutation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    aggregate_type: str = Field(min_length=1)
    aggregate_id: str = Field(min_length=1)
    aggregate_version: str = Field(min_length=1)
    occurred_at: datetime
    payload: dict[str, Any]
    schema_version: str = "v1"
    sequence: int | None = Field(default=None, ge=0)


class SnapshotRequired(BaseModel):
    """Explicit reconnect instruction; events are never authoritative state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resource_id: str = Field(min_length=1)
    reason: Literal["RECONNECT", "EVENT_GAP", "STALE_CLIENT"] = "RECONNECT"
    must_refetch_snapshot: Literal[True] = True


class ReconnectState(BaseModel):
    model_config = ConfigDict(frozen=False, extra="forbid")

    resource_id: str = Field(min_length=1)
    snapshot_version: str | None = None
    must_refetch_snapshot: bool = True
    writes_enabled: bool = False

    def on_reconnect(self) -> SnapshotRequired:
        self.snapshot_version = None
        self.must_refetch_snapshot = True
        self.writes_enabled = False
        return SnapshotRequired(resource_id=self.resource_id)

    def accept_snapshot(self, version: str) -> None:
        if not version.strip():
            raise ValueError("snapshot version must not be blank")
        self.snapshot_version = version
        self.must_refetch_snapshot = False
        self.writes_enabled = True

    def assert_writes_enabled(self, request_id: str) -> None:
        if not self.writes_enabled or self.must_refetch_snapshot:
            raise ProblemError(
                Problem(
                    title="Authoritative snapshot required",
                    status=409,
                    detail=(
                        "Fetch the resource snapshot before issuing "
                        "state-dependent writes."
                    ),
                    code="SNAPSHOT_REQUIRED",
                    request_id=request_id,
                    retryable=True,
                )
            )


def reconnect_snapshot_required(resource_id: str) -> SnapshotRequired:
    return SnapshotRequired(resource_id=resource_id)


def utc_now() -> datetime:
    return datetime.now(UTC)
