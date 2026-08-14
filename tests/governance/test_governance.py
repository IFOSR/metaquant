from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.governance.approval import (
    ApprovalDecision,
    Decision,
    Waiver,
)
from quant_platform.governance.lockbox import build_lockbox
from quant_platform.governance.report import EvidenceRef, ResearchReport


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


def test_lockbox_unlocks_with_both_keys() -> None:
    box = build_lockbox(
        box_id="box-1",
        sealed_hash="a" * 64,
        guard1_key="key-one",
        guard2_key="key-two",
    )

    assert box.unlock("key-one", "key-two")
    # order does not matter
    assert box.unlock("key-two", "key-one")


def test_lockbox_rejects_wrong_key() -> None:
    box = build_lockbox(
        box_id="box-1",
        sealed_hash="a" * 64,
        guard1_key="key-one",
        guard2_key="key-two",
    )

    assert not box.unlock("key-one", "key-three")
    assert not box.unlock("key-three", "key-two")


def test_lockbox_rejects_same_key() -> None:
    box = build_lockbox(
        box_id="box-1",
        sealed_hash="a" * 64,
        guard1_key="key-one",
        guard2_key="key-two",
    )

    assert not box.unlock("key-one", "key-one")


def test_lockbox_rejects_identical_guards() -> None:
    with pytest.raises(ValueError):
        build_lockbox(
            box_id="box-1",
            sealed_hash="a" * 64,
            guard1_key="same",
            guard2_key="same",
        )


def report() -> ResearchReport:
    return ResearchReport(
        report_id="report-1",
        subject_hash="a" * 64,
        evidence=(
            EvidenceRef("e1", "factor_version", "b" * 64),
            EvidenceRef("e2", "snapshot", "c" * 64),
        ),
        metrics=(("mean_ic", "0.042"), ("icir", "0.55")),
        narrative="Factor shows stable OOS IC.",
    )


def test_report_sign_and_verify() -> None:
    signed = report().sign(b"secret-key")

    assert signed.verify(b"secret-key")


def test_report_verify_fails_with_wrong_key() -> None:
    signed = report().sign(b"secret-key")

    assert not signed.verify(b"other-key")


def test_report_content_hash_excludes_signature() -> None:
    unsigned = report()
    signed = unsigned.sign(b"secret-key")

    assert signed.content_hash() == unsigned.content_hash()


def test_report_rejects_duplicate_evidence_refs() -> None:
    with pytest.raises(ValueError):
        ResearchReport(
            report_id="r",
            subject_hash="a" * 64,
            evidence=(
                EvidenceRef("e1", "factor_version", "b" * 64),
                EvidenceRef("e1", "snapshot", "c" * 64),
            ),
            metrics=(),
            narrative="n",
        )


def test_evidence_ref_rejects_bad_kind() -> None:
    with pytest.raises(ValueError):
        EvidenceRef("e1", "not_a_kind", "b" * 64)
