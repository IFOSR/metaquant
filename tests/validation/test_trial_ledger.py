from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.validation.trial_ledger import (
    TrialDisposition,
    TrialLedger,
    TrialLedgerEntry,
)


def entry(entry_id: str = "trial-001") -> TrialLedgerEntry:
    return TrialLedgerEntry(
        entry_id=entry_id,
        factor_ir_hash="a" * 64,
        policy_id="policy://cn-a-daily-factor/v1",
        decision_time=datetime(2026, 8, 5, 16, tzinfo=UTC),
        result_hash="b" * 64,
        disposition=TrialDisposition.ACCEPTED,
    )


def test_append_is_immutable() -> None:
    ledger = TrialLedger()

    appended = ledger.append(entry("trial-001"))

    assert ledger.entries == ()
    assert [item.entry_id for item in appended.entries] == ["trial-001"]


def test_append_rejects_duplicate_id() -> None:
    ledger = TrialLedger((entry("trial-001"),))

    with pytest.raises(ValueError, match="unique"):
        ledger.append(entry("trial-001"))


def test_content_hash_is_deterministic() -> None:
    ledger = TrialLedger((entry("trial-001"), entry("trial-002")))

    assert ledger.content_hash() == ledger.content_hash()


def test_empty_ledger_payload() -> None:
    assert TrialLedger().payload() == {
        "schema_version": "trial-ledger/v1",
        "entries": [],
    }


def test_entry_rejects_naive_time() -> None:
    with pytest.raises(ValueError):
        TrialLedgerEntry(
            entry_id="trial-001",
            factor_ir_hash="a" * 64,
            policy_id="policy://cn-a-daily-factor/v1",
            decision_time=datetime(2026, 8, 5, 16),
            result_hash="b" * 64,
            disposition=TrialDisposition.ACCEPTED,
        )


def test_entry_coerces_string_disposition() -> None:
    coerced = TrialLedgerEntry(
        entry_id="trial-001",
        factor_ir_hash="a" * 64,
        policy_id="policy://cn-a-daily-factor/v1",
        decision_time=datetime(2026, 8, 5, 16, tzinfo=UTC),
        result_hash="b" * 64,
        disposition="ACCEPTED",  # type: ignore[arg-type]
    )

    assert coerced.disposition is TrialDisposition.ACCEPTED
