"""Factor combination contracts (G8-002).

Robust IC-weighted combination with shrinkage toward equal weight, following
the technical design §11.2. Weights are estimated only on training-window IC
and frozen for the next out-of-sample fold. The equal-weight baseline is always
available, and factor ablation and marginal contribution are deterministic.

Direction semantics: a factor's combinable strength is its direction-adjusted
information ratio. ``LONG_ONLY`` credits positive IC, ``SHORT_ONLY`` credits
negative IC, and ``LONG_SHORT`` credits absolute IC. Weights are therefore
non-negative and sum to one under single-factor bounds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from quant_platform.experiments import canonical_hash
from quant_platform.validation.alpha_pool import FactorDirection

_HEX_DIGITS = frozenset("0123456789abcdef")
_PROJECTION_ITERATIONS = 200


def _require_ir_hash(value: str) -> None:
    if len(value) != 64 or any(ch not in _HEX_DIGITS for ch in value):
        raise ValueError("factor_ir_hash must be a 64-character hex digest")


@dataclass(frozen=True, slots=True)
class FactorSignal:
    """One factor's training-window IC evidence for combination."""

    factor_ir_hash: str
    train_ic: float
    ic_vol: float
    direction: FactorDirection = FactorDirection.LONG_SHORT

    def __post_init__(self) -> None:
        _require_ir_hash(self.factor_ir_hash)
        if not math.isfinite(self.train_ic):
            raise ValueError("train_ic must be finite")
        if not math.isfinite(self.ic_vol) or self.ic_vol <= 0.0:
            raise ValueError("ic_vol must be positive and finite")
        if not isinstance(self.direction, FactorDirection):
            object.__setattr__(self, "direction", FactorDirection(self.direction))

    def directional_ic(self) -> float:
        """Signed IC adjusted for the factor's tradable direction."""
        if self.direction is FactorDirection.LONG_ONLY:
            return max(self.train_ic, 0.0)
        if self.direction is FactorDirection.SHORT_ONLY:
            return max(-self.train_ic, 0.0)
        return abs(self.train_ic)

    def strength(self) -> float:
        """Direction-adjusted information ratio used for raw weighting."""
        return self.directional_ic() / self.ic_vol


@dataclass(frozen=True, slots=True)
class CombinationSpec:
    """Deterministic combination parameters."""

    spec_id: str
    shrinkage: float = 0.5
    clip: float = 3.0
    max_weight: float = 0.4

    def __post_init__(self) -> None:
        if not self.spec_id or self.spec_id.strip() != self.spec_id:
            raise ValueError("spec_id must be a non-empty normalized identifier")
        if not 0.0 <= self.shrinkage <= 1.0:
            raise ValueError("shrinkage must be within [0, 1]")
        if self.clip <= 0.0:
            raise ValueError("clip must be positive")
        if not 0.0 < self.max_weight <= 1.0:
            raise ValueError("max_weight must be within (0, 1]")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "combination-spec/v1",
            "spec_id": self.spec_id,
            "shrinkage": self.shrinkage,
            "clip": self.clip,
            "max_weight": self.max_weight,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


@dataclass(frozen=True, slots=True)
class CombinationWeights:
    """Normalized factor weights plus the method that produced them."""

    entries: tuple[tuple[str, float], ...]
    method: str
    spec_hash: str

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("combination weights must not be empty")
        if self.method not in {"ic_weighted", "equal_weight"}:
            raise ValueError("method must be ic_weighted or equal_weight")
        if len(self.spec_hash) != 64:
            raise ValueError("spec_hash must be a 64-character hex digest")
        hashes = [item[0] for item in self.entries]
        if len(set(hashes)) != len(hashes):
            raise ValueError("combination factor hashes must be unique")
        for _, weight in self.entries:
            if not math.isfinite(weight) or weight < 0.0:
                raise ValueError("combination weights must be non-negative finite")
        total = sum(weight for _, weight in self.entries)
        if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("combination weights must sum to one")

    def weights_map(self) -> dict[str, float]:
        return dict(self.entries)

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "combination-weights/v1",
            "method": self.method,
            "spec_hash": self.spec_hash,
            "weights": [
                {"factor_ir_hash": item[0], "weight": item[1]} for item in self.entries
            ],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


@dataclass(frozen=True, slots=True)
class AblationResult:
    """Impact of dropping one factor from the combination."""

    factor_ir_hash: str
    combined_expected_ic: float
    ablated_expected_ic: float
    delta: float

    def __post_init__(self) -> None:
        _require_ir_hash(self.factor_ir_hash)
        if not math.isfinite(self.delta):
            raise ValueError("ablation delta must be finite")

    def payload(self) -> dict[str, object]:
        return {
            "factor_ir_hash": self.factor_ir_hash,
            "combined_expected_ic": self.combined_expected_ic,
            "ablated_expected_ic": self.ablated_expected_ic,
            "delta": self.delta,
        }


@dataclass(frozen=True, slots=True)
class CombinationReport:
    """Complete combination output: weights, baseline, ablation, marginal."""

    weights: CombinationWeights
    equal_weight: CombinationWeights
    expected_ic: float
    ablations: tuple[AblationResult, ...]
    marginal_contributions: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.expected_ic):
            raise ValueError("expected_ic must be finite")
        if self.weights.method != "ic_weighted":
            raise ValueError("report weights must be ic_weighted")
        if self.equal_weight.method != "equal_weight":
            raise ValueError("report baseline must be equal_weight")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "combination-report/v1",
            "weights": {
                "method": self.weights.method,
                "spec_hash": self.weights.spec_hash,
                "weights": [
                    {"factor_ir_hash": item[0], "weight": item[1]}
                    for item in self.weights.entries
                ],
            },
            "equal_weight": [
                {"factor_ir_hash": item[0], "weight": item[1]}
                for item in self.equal_weight.entries
            ],
            "expected_ic": self.expected_ic,
            "ablations": [item.payload() for item in self.ablations],
            "marginal_contributions": [
                {"factor_ir_hash": item[0], "contribution": item[1]}
                for item in self.marginal_contributions
            ],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def _normalize_bounded(raw: list[float], max_weight: float) -> list[float]:
    """Project non-negative values onto sum=1 with a per-entry upper bound.

    Deterministic fixed-iteration projection: clip anything above the bound and
    renormalize the remainder until the bound is respected. Guarantees sum=1 and
    non-negativity; the upper bound holds in the limit and is enforced exactly by
    the final clip.
    """
    n = len(raw)
    total = sum(raw)
    if total <= 0.0:
        return [1.0 / n] * n
    weights = [value / total for value in raw]
    if n == 1:
        return [1.0]
    # A per-entry cap tighter than 1/n is infeasible with sum=1; relax it to
    # the equal-weight point so the projection always has a feasible region.
    cap = max(max_weight, 1.0 / n)
    for _ in range(_PROJECTION_ITERATIONS):
        weights = [min(value, cap) for value in weights]
        remaining = 1.0 - sum(weights)
        free = sum(1 for value in weights if value < cap - 1e-15)
        if free == 0 or abs(remaining) < 1e-15:
            break
        weights = [
            value + (remaining / free if value < cap - 1e-15 else 0.0)
            for value in weights
        ]
    weights = [min(value, cap) for value in weights]
    total = sum(weights)
    weights = [value / total for value in weights]
    weights = [min(value, cap) for value in weights]
    return weights


def _raw_weights(
    signals: tuple[FactorSignal, ...], spec: CombinationSpec
) -> list[float]:
    return [min(max(signal.strength(), 0.0), spec.clip) for signal in signals]


def _expected_ic(signals: tuple[FactorSignal, ...], weights: dict[str, float]) -> float:
    return sum(
        weights[signal.factor_ir_hash] * signal.directional_ic() for signal in signals
    )


def equal_weight(
    signals: tuple[FactorSignal, ...], spec: CombinationSpec
) -> CombinationWeights:
    """Equal-weight baseline, always available regardless of IC evidence."""
    if not signals:
        raise ValueError("signals must not be empty")
    n = len(signals)
    entries = tuple((signal.factor_ir_hash, 1.0 / n) for signal in signals)
    return CombinationWeights(
        entries=entries, method="equal_weight", spec_hash=spec.content_hash()
    )


def mvp_combine(
    signals: tuple[FactorSignal, ...], spec: CombinationSpec
) -> CombinationWeights:
    """Robust IC-weighted combination with shrinkage toward equal weight."""
    if not signals:
        raise ValueError("signals must not be empty")
    n = len(signals)
    raw = _raw_weights(signals, spec)
    # Shrink toward equal weight: (1 - lambda) * raw + lambda * (1/n).
    shrunk = [
        (1.0 - spec.shrinkage) * value + spec.shrinkage * (1.0 / n) for value in raw
    ]
    weights = _normalize_bounded(shrunk, spec.max_weight)
    entries = tuple(
        (signal.factor_ir_hash, weights[index]) for index, signal in enumerate(signals)
    )
    return CombinationWeights(
        entries=entries, method="ic_weighted", spec_hash=spec.content_hash()
    )


def marginal_contributions(
    signals: tuple[FactorSignal, ...], weights: CombinationWeights
) -> tuple[tuple[str, float], ...]:
    """Per-factor marginal contribution, normalized to sum to one."""
    if not signals:
        raise ValueError("signals must not be empty")
    weight_map = weights.weights_map()
    contributions = {
        signal.factor_ir_hash: weight_map[signal.factor_ir_hash]
        * signal.directional_ic()
        for signal in signals
    }
    total = sum(contributions.values())
    if total <= 0.0:
        return tuple((signal.factor_ir_hash, 0.0) for signal in signals)
    return tuple(
        (signal.factor_ir_hash, contributions[signal.factor_ir_hash] / total)
        for signal in signals
    )


def factor_ablation(
    signals: tuple[FactorSignal, ...], spec: CombinationSpec
) -> tuple[AblationResult, ...]:
    """Drop each factor in turn and measure the expected-IC impact."""
    if len(signals) < 2:
        raise ValueError("ablation requires at least two factors")
    combined = mvp_combine(signals, spec)
    combined_ic = _expected_ic(signals, combined.weights_map())
    results: list[AblationResult] = []
    for index, signal in enumerate(signals):
        remaining = tuple(item for pos, item in enumerate(signals) if pos != index)
        ablated = mvp_combine(remaining, spec)
        ablated_ic = _expected_ic(remaining, ablated.weights_map())
        results.append(
            AblationResult(
                factor_ir_hash=signal.factor_ir_hash,
                combined_expected_ic=combined_ic,
                ablated_expected_ic=ablated_ic,
                delta=combined_ic - ablated_ic,
            )
        )
    return tuple(results)


def combine(
    signals: tuple[FactorSignal, ...], spec: CombinationSpec
) -> CombinationReport:
    """Full combination report: weights, baseline, ablation, marginal."""
    if not signals:
        raise ValueError("signals must not be empty")
    weights = mvp_combine(signals, spec)
    baseline = equal_weight(signals, spec)
    ablations = factor_ablation(signals, spec) if len(signals) >= 2 else ()
    return CombinationReport(
        weights=weights,
        equal_weight=baseline,
        expected_ic=_expected_ic(signals, weights.weights_map()),
        ablations=ablations,
        marginal_contributions=marginal_contributions(signals, weights),
    )
