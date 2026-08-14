from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quant_platform.governance.approval import (
    ApprovalDecision,
    ApprovalWorkflow,
    Decision,
    WorkflowState,
)

SUBJECT = "ab" * 32


def now() -> datetime:
    return datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def workflow() -> ApprovalWorkflow:
    return ApprovalWorkflow(
        workflow_id="wf_1",
        subject_hash=SUBJECT,
        subject_kind="promotion",
        required_approvals=2,
        decisions=(),
        created_at=now(),
        expires_at=now() + timedelta(days=7),
    )


def decision(actor: str, choice: Decision, at: datetime) -> ApprovalDecision:
    return ApprovalDecision(
        decision_id=f"decision_{actor}",
        target_hash=SUBJECT,
        actor=actor,
        decision=choice,
        reason="reviewed",
        decided_at=at,
    )


def test_requires_two_distinct_approvals() -> None:
    wf = workflow()
    assert wf.state(now()) is WorkflowState.PENDING

    wf = wf.sign(decision("lead", Decision.APPROVE, now()), now())
    assert wf.state(now()) is WorkflowState.PENDING

    wf = wf.sign(decision("risk", Decision.APPROVE, now()), now())
    assert wf.state(now()) is WorkflowState.APPROVED


def test_any_rejection_fails_workflow() -> None:
    wf = workflow()
    wf = wf.sign(decision("lead", Decision.REJECT, now()), now())

    assert wf.state(now()) is WorkflowState.REJECTED


def test_duplicate_actor_cannot_sign_twice() -> None:
    wf = workflow().sign(decision("lead", Decision.APPROVE, now()), now())

    with pytest.raises(ValueError, match="already signed"):
        wf.sign(decision("lead", Decision.APPROVE, now()), now())


def test_workflow_expires() -> None:
    wf = workflow()
    later = now() + timedelta(days=8)

    assert wf.state(later) is WorkflowState.EXPIRED
    with pytest.raises(ValueError, match="not pending"):
        wf.sign(decision("lead", Decision.APPROVE, later), later)


def test_signature_must_target_subject_hash() -> None:
    other_hash = "cd" * 32
    wrong = ApprovalDecision(
        decision_id="decision_wrong",
        target_hash=other_hash,
        actor="lead",
        decision=Decision.APPROVE,
        reason="reviewed",
        decided_at=now(),
    )

    with pytest.raises(ValueError, match="subject"):
        workflow().sign(wrong, now())


def test_cannot_sign_after_terminal_state() -> None:
    wf = workflow()
    wf = wf.sign(decision("lead", Decision.APPROVE, now()), now())
    wf = wf.sign(decision("risk", Decision.APPROVE, now()), now())
    assert wf.state(now()) is WorkflowState.APPROVED

    with pytest.raises(ValueError, match="not pending"):
        wf.sign(decision("audit", Decision.APPROVE, now()), now())


def test_workflow_rejects_single_approval_requirement() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        ApprovalWorkflow(
            workflow_id="wf_bad",
            subject_hash=SUBJECT,
            subject_kind="promotion",
            required_approvals=1,
            decisions=(),
            created_at=now(),
            expires_at=now() + timedelta(days=7),
        )
