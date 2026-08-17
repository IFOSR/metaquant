"""Promotion scoring contracts (G7, Gate 5).

Promotion uses a hard-gate + scorecard decision, not a single blended score.
Hard gates reject outright; quarantine thresholds sideline suspiciously strong
results; the weighted scorecard decides promotion only after both clear.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast

from quant_platform.experiments import canonical_hash
from quant_platform.validation.policy import ICSign

_VALID_MARKETS = frozenset({"CN_A", "CN_COMMODITY_FUTURES"})
_WEIGHTS = (
    "effect",
    "stability",
    "independence",
    "cost_value",
    "interpretability",
)


class PromotionDisposition(str, Enum):
    PROMOTE = "PROMOTE"
    REJECT = "REJECT"
    QUARANTINE = "QUARANTINE"


@dataclass(frozen=True, slots=True)
class GateResult:
    name: str
    passed: bool
    observed: float | None
    threshold: float | None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    policy_id: str
    market: str
    min_coverage: float
    min_observations: int
    min_oos_ic: float
    fdr_bound: float
    min_capacity: float
    effect_weight: float = 0.25
    stability_weight: float = 0.25
    independence_weight: float = 0.20
    cost_value_weight: float = 0.20
    interpretability_weight: float = 0.10
    pass_line: float = 0.6
    quarantine_ic: float = 0.2
    quarantine_sharpe: float = 5.0

    def __post_init__(self) -> None:
        if not self.policy_id or self.policy_id.strip() != self.policy_id:
            raise ValueError("policy_id must be a non-empty normalized identifier")
        if self.market not in _VALID_MARKETS:
            raise ValueError("market must be CN_A or CN_COMMODITY_FUTURES")
        if not 0.0 <= self.min_coverage <= 1.0:
            raise ValueError("min_coverage must be within [0, 1]")
        if self.min_observations < 1:
            raise ValueError("min_observations must be positive")
        if self.min_oos_ic < 0:
            raise ValueError("min_oos_ic must be non-negative")
        if not 0.0 <= self.fdr_bound <= 1.0:
            raise ValueError("fdr_bound must be within [0, 1]")
        if self.min_capacity < 0:
            raise ValueError("min_capacity must be non-negative")
        if not 0.0 <= self.pass_line <= 1.0:
            raise ValueError("pass_line must be within [0, 1]")
        weights = (
            self.effect_weight,
            self.stability_weight,
            self.independence_weight,
            self.cost_value_weight,
            self.interpretability_weight,
        )
        if not all(w >= 0 for w in weights):
            raise ValueError("scorecard weights must be non-negative")
        total = sum(weights)
        if not abs(total - 1.0) < 1e-9:
            raise ValueError("scorecard weights must sum to 1.0")

    def weights(self) -> dict[str, float]:
        return {
            "effect": self.effect_weight,
            "stability": self.stability_weight,
            "independence": self.independence_weight,
            "cost_value": self.cost_value_weight,
            "interpretability": self.interpretability_weight,
        }

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "promotion-policy/v1",
            "policy_id": self.policy_id,
            "market": self.market,
            "min_coverage": self.min_coverage,
            "min_observations": self.min_observations,
            "min_oos_ic": self.min_oos_ic,
            "fdr_bound": self.fdr_bound,
            "min_capacity": self.min_capacity,
            "scorecard_weights": self.weights(),
            "pass_line": self.pass_line,
            "quarantine_ic": self.quarantine_ic,
            "quarantine_sharpe": self.quarantine_sharpe,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


class PromotionPolicyCatalog(Protocol):
    def resolve(self, policy_id: str) -> PromotionPolicy: ...


class InMemoryPromotionPolicyCatalog:
    def __init__(self, policies: tuple[PromotionPolicy, ...]) -> None:
        self._policies = {str(item.policy_id): item for item in policies}
        if len(self._policies) != len(policies):
            raise ValueError("promotion policy ids must be unique")

    def resolve(self, policy_id: str) -> PromotionPolicy:
        try:
            return self._policies[policy_id]
        except KeyError as exc:
            raise ValueError("PROMOTION_POLICY_NOT_REGISTERED") from exc


class JsonPromotionPolicyCatalog(InMemoryPromotionPolicyCatalog):
    @classmethod
    def from_path(cls, path: Path) -> JsonPromotionPolicyCatalog:
        document = json.loads(path.read_text())
        if not isinstance(document, list):
            raise ValueError("promotion policy catalog must be a JSON array")
        policies = tuple(
            PromotionPolicy(
                policy_id=str(item["policy_id"]),
                market=str(item["market"]),
                min_coverage=float(item["min_coverage"]),
                min_observations=int(item["min_observations"]),
                min_oos_ic=float(item["min_oos_ic"]),
                fdr_bound=float(item["fdr_bound"]),
                min_capacity=float(item["min_capacity"]),
                effect_weight=float(item.get("effect_weight", 0.25)),
                stability_weight=float(item.get("stability_weight", 0.25)),
                independence_weight=float(item.get("independence_weight", 0.20)),
                cost_value_weight=float(item.get("cost_value_weight", 0.20)),
                interpretability_weight=float(
                    item.get("interpretability_weight", 0.10)
                ),
                pass_line=float(item.get("pass_line", 0.6)),
                quarantine_ic=float(item.get("quarantine_ic", 0.2)),
                quarantine_sharpe=float(item.get("quarantine_sharpe", 5.0)),
            )
            for item in cast(list[dict[str, Any]], document)
        )
        return cls(policies)


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    coverage: float | None
    observations: int | None
    oos_ic: float | None
    expected_direction: ICSign
    fdr_qvalue: float | None
    capacity_aum: float | None
    sharpe: float | None
    effect_score: float | None
    stability_score: float | None
    independence_score: float | None
    cost_value_score: float | None
    interpretability_score: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.expected_direction, ICSign):
            object.__setattr__(
                self, "expected_direction", ICSign(self.expected_direction)
            )
        for name in _WEIGHTS:
            score = getattr(self, f"{name}_score")
            if score is not None and not 0.0 <= score <= 1.0:
                raise ValueError(f"{name}_score must be within [0, 1]")


def cross_check_evidence(
    evidence: CandidateEvidence, report_payload: dict[str, object]
) -> CandidateEvidence:
    """Cross-check caller evidence against a stored validation report payload.

    The stored report is the authority for ``coverage`` and ``observations``.
    Caller values that disagree raise ``ValueError``, and the returned evidence
    carries the stored values so gates evaluate server-side numbers.
    """
    quality_raw = report_payload.get("data_quality")
    if not isinstance(quality_raw, dict):
        raise ValueError("VALIDATION_REPORT_INCOMPLETE")
    server_coverage = quality_raw.get("coverage_ratio")
    server_observations = quality_raw.get("observation_count")
    if not isinstance(server_coverage, int | float) or not isinstance(
        server_observations, int | float
    ):
        raise ValueError("VALIDATION_REPORT_INCOMPLETE")
    if (
        evidence.coverage is not None
        and abs(evidence.coverage - float(server_coverage)) > 1e-9
    ):
        raise ValueError("EVIDENCE_MISMATCH:coverage")
    if evidence.observations is not None and evidence.observations != int(
        server_observations
    ):
        raise ValueError("EVIDENCE_MISMATCH:observations")

    return replace(
        evidence,
        coverage=float(server_coverage),
        observations=int(server_observations),
    )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    disposition: PromotionDisposition
    gates: tuple[GateResult, ...]
    component_scores: tuple[tuple[str, float], ...]
    total_score: float | None
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, PromotionDisposition):
            object.__setattr__(
                self, "disposition", PromotionDisposition(self.disposition)
            )
        if not self.rationale:
            raise ValueError("rationale must not be empty")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "promotion-decision/v1",
            "disposition": self.disposition.value,
            "gates": [
                {
                    "name": gate.name,
                    "passed": gate.passed,
                    "observed": gate.observed,
                    "threshold": gate.threshold,
                    "note": gate.note,
                }
                for gate in self.gates
            ],
            "component_scores": [list(item) for item in self.component_scores],
            "total_score": self.total_score,
            "rationale": self.rationale,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def _gate(
    name: str,
    passed: bool,
    observed: float | None,
    threshold: float | None,
    note: str | None = None,
) -> GateResult:
    return GateResult(
        name=name, passed=passed, observed=observed, threshold=threshold, note=note
    )


def _direction_consistent(oos_ic: float | None, expected: ICSign) -> bool:
    if oos_ic is None:
        return False
    if expected is ICSign.ANY:
        return True
    if expected is ICSign.POSITIVE:
        return oos_ic > 0
    return oos_ic < 0


def evaluate_promotion(
    evidence: CandidateEvidence, policy: PromotionPolicy
) -> PromotionDecision:
    gates: list[GateResult] = []

    coverage = evidence.coverage
    gates.append(
        _gate(
            "data_quality.coverage",
            coverage is not None and coverage >= policy.min_coverage,
            coverage,
            policy.min_coverage,
        )
    )
    observations = evidence.observations
    gates.append(
        _gate(
            "data_quality.observations",
            observations is not None and observations >= policy.min_observations,
            float(observations) if observations is not None else None,
            float(policy.min_observations),
        )
    )
    oos_ic = evidence.oos_ic
    direction_ok = _direction_consistent(oos_ic, evidence.expected_direction)
    gates.append(
        _gate(
            "oos.direction",
            direction_ok and oos_ic is not None,
            oos_ic,
            policy.min_oos_ic,
        )
    )
    gates.append(
        _gate(
            "oos.magnitude",
            oos_ic is not None and abs(oos_ic) >= policy.min_oos_ic,
            abs(oos_ic) if oos_ic is not None else None,
            policy.min_oos_ic,
        )
    )
    fdr = evidence.fdr_qvalue
    gates.append(
        _gate(
            "false_discovery.fdr",
            fdr is not None and fdr <= policy.fdr_bound,
            fdr,
            policy.fdr_bound,
        )
    )
    capacity = evidence.capacity_aum
    gates.append(
        _gate(
            "capacity.minimum",
            capacity is not None and capacity >= policy.min_capacity,
            capacity,
            policy.min_capacity,
        )
    )

    if not all(gate.passed for gate in gates):
        failed = ", ".join(gate.name for gate in gates if not gate.passed)
        return PromotionDecision(
            disposition=PromotionDisposition.REJECT,
            gates=tuple(gates),
            component_scores=(),
            total_score=None,
            rationale=f"hard gate(s) failed: {failed}",
        )

    if (oos_ic is not None and abs(oos_ic) > policy.quarantine_ic) or (
        evidence.sharpe is not None and evidence.sharpe > policy.quarantine_sharpe
    ):
        return PromotionDecision(
            disposition=PromotionDisposition.QUARANTINE,
            gates=tuple(gates),
            component_scores=(),
            total_score=None,
            rationale="suspiciously strong result: quarantine for investigation",
        )

    weights = policy.weights()
    scores: list[tuple[str, float]] = []
    total = 0.0
    for name in _WEIGHTS:
        score = getattr(evidence, f"{name}_score")
        if score is None:
            return PromotionDecision(
                disposition=PromotionDisposition.REJECT,
                gates=tuple(gates),
                component_scores=(),
                total_score=None,
                rationale=f"missing scorecard component: {name}",
            )
        scores.append((name, score))
        total += weights[name] * score

    disposition = (
        PromotionDisposition.PROMOTE
        if total >= policy.pass_line
        else PromotionDisposition.REJECT
    )
    return PromotionDecision(
        disposition=disposition,
        gates=tuple(gates),
        component_scores=tuple(scores),
        total_score=total,
        rationale=(
            "all hard gates passed; scorecard "
            f"{total:.4f} "
            f"{'meets' if disposition is PromotionDisposition.PROMOTE else 'below'} "
            f"pass line {policy.pass_line:.4f}"
        ),
    )
