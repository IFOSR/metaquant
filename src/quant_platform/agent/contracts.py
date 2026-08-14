"""Research Agent contracts (G12-001).

A single ``ResearchProposal`` contract that every Agent role (Intake,
Hypothesis, Critic, Paper, Formula, Mapping) must emit. Agent output can only
land in structured schemas; it can never write directly to the deterministic
kernel, the PostgreSQL store, a GateDecision, the Alpha Pool, or a
StrategyPackage.
"""

from __future__ import annotations

from dataclasses import dataclass

from quant_platform.experiments import canonical_hash

_VALID_SIGNS = frozenset({"positive", "negative", "unknown"})


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


@dataclass(frozen=True, slots=True)
class CandidateFactor:
    factor_id: str
    economic_mechanism: str
    inputs: tuple[str, ...]
    formula: str
    direction: str
    lookback_days: int

    def __post_init__(self) -> None:
        _require_identifier(self.factor_id, "factor_id")
        if not self.economic_mechanism:
            raise ValueError("economic_mechanism must not be empty")
        if not self.inputs:
            raise ValueError("inputs must not be empty")
        if not self.formula:
            raise ValueError("formula must not be empty")
        if self.direction not in _VALID_SIGNS:
            raise ValueError("direction must be positive, negative, or unknown")
        if self.lookback_days <= 0:
            raise ValueError("lookback_days must be positive")

    def payload(self) -> dict[str, object]:
        return {
            "factor_id": self.factor_id,
            "economic_mechanism": self.economic_mechanism,
            "inputs": list(self.inputs),
            "formula": self.formula,
            "direction": self.direction,
            "lookback_days": self.lookback_days,
        }


@dataclass(frozen=True, slots=True)
class FalsificationTest:
    test_id: str
    description: str
    expected_if_true: str
    expected_if_false: str

    def __post_init__(self) -> None:
        _require_identifier(self.test_id, "test_id")
        if (
            not self.description
            or not self.expected_if_true
            or not self.expected_if_false
        ):
            raise ValueError("falsification test fields must not be empty")

    def payload(self) -> dict[str, object]:
        return {
            "test_id": self.test_id,
            "description": self.description,
            "expected_if_true": self.expected_if_true,
            "expected_if_false": self.expected_if_false,
        }


@dataclass(frozen=True, slots=True)
class DataRequest:
    dataset_id: str
    fields: tuple[str, ...]
    purpose: str = "RESEARCH"

    def __post_init__(self) -> None:
        _require_identifier(self.dataset_id, "dataset_id")
        if not self.fields:
            raise ValueError("fields must not be empty")

    def payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "fields": list(self.fields),
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class Uncertainty:
    description: str
    severity: str

    def __post_init__(self) -> None:
        if not self.description:
            raise ValueError("uncertainty description must not be empty")
        if self.severity not in {"low", "medium", "high"}:
            raise ValueError("severity must be low, medium, or high")

    def payload(self) -> dict[str, object]:
        return {"description": self.description, "severity": self.severity}


@dataclass(frozen=True, slots=True)
class ResearchProposal:
    job_id: str
    hypothesis: str
    mechanism: str
    expected_sign: str
    candidate_factors: tuple[CandidateFactor, ...]
    falsification_tests: tuple[FalsificationTest, ...]
    data_requests: tuple[DataRequest, ...]
    evidence_refs: tuple[str, ...]
    uncertainty: tuple[Uncertainty, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.job_id, "job_id")
        if not self.hypothesis or not self.mechanism:
            raise ValueError("hypothesis and mechanism must not be empty")
        if self.expected_sign not in _VALID_SIGNS:
            raise ValueError("expected_sign must be positive, negative, or unknown")
        factor_ids = [item.factor_id for item in self.candidate_factors]
        if len(set(factor_ids)) != len(factor_ids):
            raise ValueError("candidate factor ids must be unique")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "research-proposal/v1",
            "job_id": self.job_id,
            "hypothesis": self.hypothesis,
            "mechanism": self.mechanism,
            "expected_sign": self.expected_sign,
            "candidate_factors": [item.payload() for item in self.candidate_factors],
            "falsification_tests": [
                item.payload() for item in self.falsification_tests
            ],
            "data_requests": [item.payload() for item in self.data_requests],
            "evidence_refs": list(self.evidence_refs),
            "uncertainty": [item.payload() for item in self.uncertainty],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())
