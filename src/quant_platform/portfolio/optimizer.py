"""Constrained portfolio optimizer (G8-003).

Deterministic projected-gradient optimizer for the technical design §11.3
objective::

    minimize  -alpha'w + lambda_risk * w'Cov w
              + lambda_turnover * sum|w - w_prev|
              + lambda_concentration * sum w^2

Hard constraints are full investment (sum w = 1), long-only (w >= 0), a single
asset cap, and an optional holding-count cap (top-k truncation). Turnover is
penalized through the objective rather than projected, so the projection stays
convex. Infeasible constraints are reported as diagnostics and the result
degrades to the equal-weight baseline, never silently relaxing the constraint.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from quant_platform.experiments import canonical_hash

_PROJECTION_ITERATIONS = 200


@dataclass(frozen=True, slots=True)
class OptimizationSpec:
    """Deterministic optimizer parameters."""

    spec_id: str
    lambda_risk: float = 1.0
    lambda_turnover: float = 0.5
    lambda_concentration: float = 0.01
    iterations: int = 200
    learning_rate: float = 0.05

    def __post_init__(self) -> None:
        if not self.spec_id or self.spec_id.strip() != self.spec_id:
            raise ValueError("spec_id must be a non-empty normalized identifier")
        if self.lambda_risk < 0.0:
            raise ValueError("lambda_risk must be non-negative")
        if self.lambda_turnover < 0.0:
            raise ValueError("lambda_turnover must be non-negative")
        if self.lambda_concentration < 0.0:
            raise ValueError("lambda_concentration must be non-negative")
        if self.iterations < 1:
            raise ValueError("iterations must be positive")
        if not 0.0 < self.learning_rate < 1.0:
            raise ValueError("learning_rate must be within (0, 1)")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "optimization-spec/v1",
            "spec_id": self.spec_id,
            "lambda_risk": self.lambda_risk,
            "lambda_turnover": self.lambda_turnover,
            "lambda_concentration": self.lambda_concentration,
            "iterations": self.iterations,
            "learning_rate": self.learning_rate,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Optimizer output: weights, objective, convergence, and fallback status."""

    weights: tuple[float, ...]
    objective: float
    converged: bool
    fallback: bool
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.weights:
            raise ValueError("optimization weights must not be empty")
        for weight in self.weights:
            if not math.isfinite(weight) or weight < 0.0:
                raise ValueError("optimization weights must be non-negative finite")
        if not math.isclose(sum(self.weights), 1.0, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("optimization weights must sum to one")
        if not math.isfinite(self.objective):
            raise ValueError("objective must be finite")
        if self.fallback and not self.diagnostics:
            raise ValueError("fallback requires at least one diagnostic")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "optimization-result/v1",
            "weights": list(self.weights),
            "objective": self.objective,
            "converged": self.converged,
            "fallback": self.fallback,
            "diagnostics": list(self.diagnostics),
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def _project_simplex_box(raw: list[float], cap: float) -> list[float]:
    """Project onto {w >= 0, sum w = 1, w_i <= cap} deterministically."""
    n = len(raw)
    total = sum(raw)
    if total <= 0.0:
        return [1.0 / n] * n
    weights = [value / total for value in raw]
    if n == 1:
        return [1.0]
    effective_cap = max(cap, 1.0 / n)
    for _ in range(_PROJECTION_ITERATIONS):
        weights = [min(value, effective_cap) for value in weights]
        remaining = 1.0 - sum(weights)
        free = sum(1 for value in weights if value < effective_cap - 1e-15)
        if free == 0 or abs(remaining) < 1e-15:
            break
        weights = [
            value + (remaining / free if value < effective_cap - 1e-15 else 0.0)
            for value in weights
        ]
    weights = [min(value, effective_cap) for value in weights]
    total = sum(weights)
    return [value / total for value in weights]


def _truncate_top_k(weights: list[float], max_holdings: int) -> list[float]:
    """Keep the ``max_holdings`` largest weights, zero the rest, renormalize."""
    n = len(weights)
    if max_holdings >= n:
        return weights
    keep = sorted(range(n), key=lambda i: weights[i], reverse=True)[:max_holdings]
    keep_set = set(keep)
    truncated = [weights[i] if i in keep_set else 0.0 for i in range(n)]
    total = sum(truncated)
    if total <= 0.0:
        return [1.0 / n] * n
    return [value / total for value in truncated]


def _cov_mv(
    covariance: tuple[tuple[float, ...], ...], weights: list[float]
) -> list[float]:
    n = len(weights)
    return [sum(covariance[i][j] * weights[j] for j in range(n)) for i in range(n)]


def _objective(
    alpha: tuple[float, ...],
    covariance: tuple[tuple[float, ...], ...],
    prev: list[float],
    weights: list[float],
    spec: OptimizationSpec,
) -> float:
    n = len(weights)
    alpha_term = sum(alpha[i] * weights[i] for i in range(n))
    cov_w = _cov_mv(covariance, weights)
    risk_term = sum(weights[i] * cov_w[i] for i in range(n))
    turnover_term = sum(abs(weights[i] - prev[i]) for i in range(n))
    concentration_term = sum(weights[i] * weights[i] for i in range(n))
    return (
        -alpha_term
        + spec.lambda_risk * risk_term
        + spec.lambda_turnover * turnover_term
        + spec.lambda_concentration * concentration_term
    )


def optimize(
    alpha: tuple[float, ...],
    covariance: tuple[tuple[float, ...], ...],
    prev_weights: tuple[float, ...] | None = None,
    *,
    max_single_weight: float = 0.1,
    max_holdings: int | None = None,
    spec: OptimizationSpec | None = None,
) -> OptimizationResult:
    """Run the constrained projected-gradient optimization.

    Returns a fallback result (equal-weight) with diagnostics when constraints
    are infeasible, when inputs are degenerate, or when the optimizer fails to
    converge within the fixed iteration budget.
    """
    if spec is None:
        spec = OptimizationSpec(spec_id="opt://default/v1")

    diagnostics: list[str] = []
    n = len(alpha)
    if n == 0:
        raise ValueError("alpha must not be empty")
    if not all(math.isfinite(value) for value in alpha):
        diagnostics.append("ALPHA_NOT_FINITE")
    if len(covariance) != n or any(len(row) != n for row in covariance):
        diagnostics.append("COVARIANCE_DIMENSION_MISMATCH")
    elif not all(math.isfinite(value) for row in covariance for value in row):
        diagnostics.append("COVARIANCE_NOT_FINITE")
    elif any(
        not math.isclose(
            covariance[i][j], covariance[j][i], rel_tol=1e-9, abs_tol=1e-12
        )
        for i in range(n)
        for j in range(n)
    ):
        diagnostics.append("COVARIANCE_NOT_SYMMETRIC")
    if not 0.0 < max_single_weight <= 1.0:
        raise ValueError("max_single_weight must be within (0, 1]")
    if max_holdings is not None and max_holdings < 1:
        raise ValueError("max_holdings must be positive when provided")

    if diagnostics:
        equal = [1.0 / n] * n
        return OptimizationResult(
            weights=tuple(equal),
            objective=0.0,
            converged=False,
            fallback=True,
            diagnostics=tuple(diagnostics),
        )

    prev = list(prev_weights) if prev_weights is not None else [0.0] * n
    if len(prev) != n:
        raise ValueError("prev_weights must match alpha length")
    if any(not math.isfinite(value) or value < 0.0 for value in prev):
        raise ValueError("prev_weights must be non-negative finite")
    if prev_weights is not None and not math.isclose(
        sum(prev), 1.0, rel_tol=1e-9, abs_tol=1e-12
    ):
        raise ValueError("prev_weights must sum to one")

    # Infeasibility: a cap tighter than 1/n cannot reach full investment.
    if max_single_weight * n < 1.0 - 1e-12:
        equal = [1.0 / n] * n
        return OptimizationResult(
            weights=tuple(equal),
            objective=_objective(alpha, covariance, prev, equal, spec),
            converged=False,
            fallback=True,
            diagnostics=("MAX_SINGLE_WEIGHT_INFEASIBLE",),
        )

    # Initialize at the previous weights (fall back to equal weight when empty).
    weights = list(prev) if prev_weights is not None else [1.0 / n] * n

    converged = False
    for _ in range(spec.iterations):
        cov_w = _cov_mv(covariance, weights)
        gradient = [
            -alpha[i]
            + 2.0 * spec.lambda_risk * cov_w[i]
            + spec.lambda_turnover
            * (1.0 if weights[i] > prev[i] else -1.0 if weights[i] < prev[i] else 0.0)
            + 2.0 * spec.lambda_concentration * weights[i]
            for i in range(n)
        ]
        candidate = [weights[i] - spec.learning_rate * gradient[i] for i in range(n)]
        candidate = [max(value, 0.0) for value in candidate]
        candidate = _project_simplex_box(candidate, max_single_weight)
        if max_holdings is not None:
            candidate = _truncate_top_k(candidate, max_holdings)

        step = max(abs(candidate[i] - weights[i]) for i in range(n))
        weights = candidate
        if step < 1e-9:
            converged = True
            break

    if not converged:
        diagnostics.append("NOT_CONVERGED")

    return OptimizationResult(
        weights=tuple(weights),
        objective=_objective(alpha, covariance, prev, weights, spec),
        converged=converged,
        fallback=False,
        diagnostics=tuple(diagnostics),
    )
