from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.governance.approval import (
    ApprovalDecision,
    Decision,
    Waiver,
)


def at(day: int) -> datetime:
    return datetime(2026, 8, day, 12, tzinfo=UTC)


def test_approval_decision_is_deterministic() -> None:
    first = ApprovalDecision(
        decision_id="d1",
        target_hash="a" * 64,
        actor="lead-1",
        decision=Decision.APPROVE,
        reason="all gates passed",
        decided_at=at(1),
    )
    second = ApprovalDecision(
        decision_id="d1",
        target_hash="a" * 64,
        actor="lead-1",
        decision=Decision.APPROVE,
        reason="all gates passed",
        decided_at=at(1),
    )

    assert first == second
    assert first.content_hash() == second.content_hash()


def test_waiver_is_active_within_window() -> None:
    waiver = Waiver(
        waiver_id="w1",
        target_hash="a" * 64,
        gate_name="oos.direction",
        reason="short window",
        granted_by="lead-1",
        granted_at=at(1),
        expires_at=at(10),
    )

    assert waiver.is_active(at(5))
    assert not waiver.is_active(at(10))
    # before the grant window opens
    assert not waiver.is_active(datetime(2026, 7, 31, 12, tzinfo=UTC))


def test_waiver_requires_expiry_after_grant() -> None:
    with pytest.raises(ValueError):
        Waiver(
            waiver_id="w1",
            target_hash="a" * 64,
            gate_name="oos.direction",
            reason="bad",
            granted_by="lead-1",
            granted_at=at(10),
            expires_at=at(1),
        )
