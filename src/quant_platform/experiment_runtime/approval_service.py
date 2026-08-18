"""Approval workflow service: reads, signing, and promotion linkage.

Extracted from the experiment repository so promotion approval state lives in
its own module and the repository stays focused on the experiment lifecycle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from quant_platform.governance import (
    ApprovalDecision,
    ApprovalWorkflow,
    Decision,
    WorkflowState,
)
from quant_platform.research.models import (
    AlphaPoolFactorModel,
    ApprovalWorkflowModel,
    CombinationPoolFactorModel,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _workflow_from_model(model: ApprovalWorkflowModel) -> ApprovalWorkflow:
    decisions = tuple(
        ApprovalDecision(
            decision_id=str(item["decision_id"]),
            target_hash=str(item["target_hash"]),
            actor=str(item["actor"]),
            decision=Decision(str(item["decision"])),
            reason=str(item["reason"]),
            decided_at=_aware(datetime.fromisoformat(str(item["decided_at"]))),
        )
        for item in model.decisions
    )
    return ApprovalWorkflow(
        workflow_id=model.workflow_id,
        subject_hash=model.subject_hash,
        subject_kind=model.subject_kind,
        required_approvals=model.required_approvals,
        decisions=decisions,
        created_at=_aware(model.created_at),
        expires_at=_aware(model.expires_at),
    )


def _apply_promotion_approval(session: Session, subject_hash: str) -> None:
    pool = session.scalar(
        select(CombinationPoolFactorModel).where(
            CombinationPoolFactorModel.promotion_evidence_hash == subject_hash
        )
    )
    if pool is None:
        raise ValueError("COMBINATION_POOL_ENTRY_NOT_FOUND")
    alpha = session.get(AlphaPoolFactorModel, pool.factor_ir_hash)
    if alpha is not None:
        alpha.lifecycle_state = "PROMOTED"


def _apply_promotion_rejection(session: Session, subject_hash: str) -> None:
    pool = session.scalar(
        select(CombinationPoolFactorModel).where(
            CombinationPoolFactorModel.promotion_evidence_hash == subject_hash
        )
    )
    if pool is None:
        return
    alpha = session.get(AlphaPoolFactorModel, pool.factor_ir_hash)
    if alpha is not None:
        alpha.lifecycle_state = "REJECTED"


class ApprovalService:
    """Handles approval workflow reads, signing, and promotion linkage."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        with self._sessions() as session:
            model = session.get(ApprovalWorkflowModel, workflow_id)
            if model is None:
                return None
            workflow = _workflow_from_model(model)
            return {
                "workflow_id": model.workflow_id,
                "subject_hash": model.subject_hash,
                "subject_kind": model.subject_kind,
                "required_approvals": model.required_approvals,
                "state": workflow.state(_now()).value,
                "decisions": model.decisions,
                "created_at": model.created_at,
                "expires_at": model.expires_at,
            }

    def sign(
        self,
        *,
        workflow_id: str,
        actor_id: str,
        decision: str,
        reason: str,
    ) -> dict[str, Any]:
        """Sign an approval workflow and apply promotion linkage on final state."""
        with self._sessions.begin() as session:
            model = session.get(ApprovalWorkflowModel, workflow_id)
            if model is None:
                raise ValueError("WORKFLOW_NOT_FOUND")
            workflow = _workflow_from_model(model)
            now = _now()
            record = ApprovalDecision(
                decision_id=f"decision_{uuid4().hex}",
                target_hash=workflow.subject_hash,
                actor=actor_id,
                decision=Decision(decision),
                reason=reason,
                decided_at=now,
            )
            updated = workflow.sign(record, now)
            model.decisions = [item.payload() for item in updated.decisions]
            state = updated.state(now)
            if state is WorkflowState.APPROVED and model.subject_kind == "promotion":
                _apply_promotion_approval(session, model.subject_hash)
            elif state is WorkflowState.REJECTED and model.subject_kind == "promotion":
                _apply_promotion_rejection(session, model.subject_hash)
            return {
                "workflow_id": workflow_id,
                "state": state.value,
                "decisions": model.decisions,
            }
