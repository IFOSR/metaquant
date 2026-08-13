"""Append-only trial ledger (G5-006).

Every candidate and every tuning attempt must be recorded before a validation
is accepted, so a survivor cannot be reported without its full search history.
The ledger is immutable: ``append`` returns a new ledger and never mutates the
receiver.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from quant_platform.experiments import canonical_hash
from quant_platform.validation.contracts import _require_aware, _require_identifier


class TrialDisposition(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class TrialLedgerEntry:
    entry_id: str
    factor_ir_hash: str
    policy_id: str
    decision_time: datetime
    result_hash: str
    disposition: TrialDisposition

    def __post_init__(self) -> None:
        _require_identifier(self.entry_id, "entry_id")
        _require_identifier(self.factor_ir_hash, "factor_ir_hash")
        _require_identifier(self.policy_id, "policy_id")
        _require_aware(self.decision_time, "decision_time")
        _require_identifier(self.result_hash, "result_hash")
        if not isinstance(self.disposition, TrialDisposition):
            object.__setattr__(self, "disposition", TrialDisposition(self.disposition))

    def payload(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "factor_ir_hash": self.factor_ir_hash,
            "policy_id": self.policy_id,
            "decision_time": self.decision_time.isoformat(),
            "result_hash": self.result_hash,
            "disposition": self.disposition.value,
        }


@dataclass(frozen=True, slots=True)
class TrialLedger:
    entries: tuple[TrialLedgerEntry, ...] = ()

    def append(self, entry: TrialLedgerEntry) -> TrialLedger:
        if entry.entry_id in {item.entry_id for item in self.entries}:
            raise ValueError("trial ledger entry id must be unique")
        return TrialLedger(self.entries + (entry,))

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "trial-ledger/v1",
            "entries": [entry.payload() for entry in self.entries],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())
