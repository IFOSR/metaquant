"""Approval and waiver contracts (G11-001).

Approval decisions and waivers are immutable, append-only records bound to the
target's content hash. A waiver is an approval of a hard-gate failure with a
mandatory reason and expiry; it is never silent and always traceable.

``ApprovalWorkflow`` (G16-002) enforces the two-person rule: a subject is only
approved after ``required_approvals`` distinct actors sign, any rejection fails
it outright, and expiry is terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from quant_platform.experiments import canonical_hash

_HEX_DIGITS = frozenset("0123456789abcdef")


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(ch not in _HEX_DIGITS for ch in value):
        raise ValueError(f"{name} must be a 64-character hex digest")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class Decision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class WorkflowState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    decision_id: str
    target_hash: str
    actor: str
    decision: Decision
    reason: str
    decided_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.decision_id, "decision_id")
        _require_sha256(self.target_hash, "target_hash")
        _require_identifier(self.actor, "actor")
        if not isinstance(self.decision, Decision):
            object.__setattr__(self, "decision", Decision(self.decision))
        if not self.reason:
            raise ValueError("reason must not be empty")
        _require_aware(self.decided_at, "decided_at")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "approval-decision/v1",
            "decision_id": self.decision_id,
            "target_hash": self.target_hash,
            "actor": self.actor,
            "decision": self.decision.value,
            "reason": self.reason,
            "decided_at": self.decided_at.isoformat(),
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


@dataclass(frozen=True, slots=True)
class ApprovalWorkflow:
    """Two-person approval workflow bound to a content-addressed subject.

    The workflow stays PENDING until ``required_approvals`` distinct actors
    approve; any rejection fails it outright; a missed expiry expires it. An
    actor may sign at most once, and every signature must target the workflow
    subject hash, so signatures cannot be replayed across subjects.
    """

    workflow_id: str
    subject_hash: str
    subject_kind: str
    required_approvals: int
    decisions: tuple[ApprovalDecision, ...]
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.workflow_id, "workflow_id")
        _require_sha256(self.subject_hash, "subject_hash")
        _require_identifier(self.subject_kind, "subject_kind")
        if self.required_approvals < 2:
            raise ValueError("required_approvals must be at least 2")
        _require_aware(self.created_at, "created_at")
        _require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must follow created_at")
        actors = [item.actor for item in self.decisions]
        if len(set(actors)) != len(actors):
            raise ValueError("an actor may sign only once")
        for item in self.decisions:
            if item.target_hash != self.subject_hash:
                raise ValueError("decision target must match workflow subject")

    def state(self, now: datetime) -> WorkflowState:
        _require_aware(now, "now")
        if any(item.decision is Decision.REJECT for item in self.decisions):
            return WorkflowState.REJECTED
        approvals = sum(
            1 for item in self.decisions if item.decision is Decision.APPROVE
        )
        if approvals >= self.required_approvals:
            return WorkflowState.APPROVED
        if now >= self.expires_at:
            return WorkflowState.EXPIRED
        return WorkflowState.PENDING

    def sign(self, decision: ApprovalDecision, now: datetime) -> ApprovalWorkflow:
        _require_aware(now, "now")
        if self.state(now) is not WorkflowState.PENDING:
            raise ValueError("workflow is not pending")
        if decision.target_hash != self.subject_hash:
            raise ValueError("decision target must match workflow subject")
        if any(item.actor == decision.actor for item in self.decisions):
            raise ValueError("actor has already signed")
        return replace(self, decisions=(*self.decisions, decision))

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "approval-workflow/v1",
            "workflow_id": self.workflow_id,
            "subject_hash": self.subject_hash,
            "subject_kind": self.subject_kind,
            "required_approvals": self.required_approvals,
            "decisions": [item.payload() for item in self.decisions],
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


@dataclass(frozen=True, slots=True)
class Waiver:
    waiver_id: str
    target_hash: str
    gate_name: str
    reason: str
    granted_by: str
    granted_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.waiver_id, "waiver_id")
        _require_sha256(self.target_hash, "target_hash")
        _require_identifier(self.gate_name, "gate_name")
        if not self.reason:
            raise ValueError("reason must not be empty")
        _require_identifier(self.granted_by, "granted_by")
        _require_aware(self.granted_at, "granted_at")
        _require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.granted_at:
            raise ValueError("expires_at must follow granted_at")

    def is_active(self, now: datetime) -> bool:
        _require_aware(now, "now")
        return self.granted_at <= now < self.expires_at

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "waiver/v1",
            "waiver_id": self.waiver_id,
            "target_hash": self.target_hash,
            "gate_name": self.gate_name,
            "reason": self.reason,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())
