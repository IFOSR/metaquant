"""Research report contracts (G11-003).

A research report binds a subject (factor or strategy) to its evidence
references and metrics, and can be signed over its content hash. Evidence refs
locate each conclusion back to a factor version, data snapshot, rule version,
code version, or paper page, giving the report a verifiable lineage.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from quant_platform.experiments import canonical_hash

_HEX_DIGITS = frozenset("0123456789abcdef")
_VALID_KINDS = frozenset({"factor_version", "snapshot", "rule", "code", "paper_page"})


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(ch not in _HEX_DIGITS for ch in value):
        raise ValueError(f"{name} must be a 64-character hex digest")


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    ref_id: str
    kind: str
    target_hash: str

    def __post_init__(self) -> None:
        _require_identifier(self.ref_id, "ref_id")
        if self.kind not in _VALID_KINDS:
            raise ValueError(f"kind must be one of {sorted(_VALID_KINDS)}")
        _require_sha256(self.target_hash, "target_hash")

    def payload(self) -> dict[str, object]:
        return {
            "ref_id": self.ref_id,
            "kind": self.kind,
            "target_hash": self.target_hash,
        }


@dataclass(frozen=True, slots=True)
class ResearchReport:
    report_id: str
    subject_hash: str
    evidence: tuple[EvidenceRef, ...]
    metrics: tuple[tuple[str, str], ...]
    narrative: str
    signature: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.report_id, "report_id")
        _require_sha256(self.subject_hash, "subject_hash")
        ref_ids = [item.ref_id for item in self.evidence]
        if len(set(ref_ids)) != len(ref_ids):
            raise ValueError("evidence ref ids must be unique")
        metric_names = [item[0] for item in self.metrics]
        if len(set(metric_names)) != len(metric_names):
            raise ValueError("metric names must be unique")
        if not self.narrative:
            raise ValueError("narrative must not be empty")
        if self.signature is not None and not _HEX_DIGITS.issuperset(self.signature):
            raise ValueError("signature must be a lowercase hex digest")

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "schema_version": "research-report/v1",
            "report_id": self.report_id,
            "subject_hash": self.subject_hash,
            "evidence": [item.payload() for item in self.evidence],
            "metrics": [{"name": item[0], "value": item[1]} for item in self.metrics],
            "narrative": self.narrative,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.unsigned_payload())

    def sign(self, key: bytes) -> ResearchReport:
        if not key:
            raise ValueError("signing key must not be empty")
        digest = hmac.new(key, self.content_hash().encode(), hashlib.sha256).hexdigest()
        return ResearchReport(
            report_id=self.report_id,
            subject_hash=self.subject_hash,
            evidence=self.evidence,
            metrics=self.metrics,
            narrative=self.narrative,
            signature=digest,
        )

    def verify(self, key: bytes) -> bool:
        if self.signature is None or not key:
            return False
        expected = hmac.new(
            key, self.content_hash().encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)
