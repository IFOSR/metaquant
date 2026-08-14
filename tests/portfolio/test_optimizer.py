from __future__ import annotations

import pytest

from quant_platform.portfolio.optimizer import (
    OptimizationSpec,
    optimize,
)


def spec() -> OptimizationSpec:
    return OptimizationSpec(spec_id="opt://test/v1")


def alpha() -> tuple[float, ...]:
    return (0.10, 0.05, 0.02)


def covariance() -> tuple[tuple[float, ...], ...]:
    return (
        (0.10, 0.00, 0.00),
        (0.00, 0.08, 0.00),
        (0.00, 0.00, 0.06),
    )


def test_optimize_sums_to_one() -> None:
    result = optimize(alpha(), covariance(), max_single_weight=0.5, spec=spec())

    assert sum(result.weights) == pytest.approx(1.0)
    assert not result.fallback


def test_optimize_prefers_high_alpha() -> None:
    result = optimize(
        alpha(),
        covariance(),
        max_single_weight=0.5,
        spec=OptimizationSpec(
            spec_id="s",
            lambda_risk=0.0,
            lambda_turnover=0.0,
            lambda_concentration=0.001,
        ),
    )

    assert result.weights[0] > result.weights[1] > result.weights[2]


def test_optimize_respects_max_single_weight() -> None:
    result = optimize(alpha(), covariance(), max_single_weight=0.4, spec=spec())

    for weight in result.weights:
        assert weight <= 0.4 + 1e-9


def test_optimize_respects_max_holdings() -> None:
    result = optimize(
        alpha(), covariance(), max_single_weight=0.8, max_holdings=2, spec=spec()
    )

    nonzero = sum(1 for weight in result.weights if weight > 1e-9)
    assert nonzero <= 2


def test_optimize_infeasible_cap_falls_back() -> None:
    result = optimize(alpha(), covariance(), max_single_weight=0.2, spec=spec())

    assert result.fallback
    assert "MAX_SINGLE_WEIGHT_INFEASIBLE" in result.diagnostics
    # fallback is equal weight
    for weight in result.weights:
        assert weight == pytest.approx(1.0 / 3.0)


def test_optimize_dimension_mismatch_falls_back() -> None:
    bad_cov = ((0.1, 0.0), (0.0, 0.08))
    result = optimize(alpha(), bad_cov, max_single_weight=0.5, spec=spec())

    assert result.fallback
    assert "COVARIANCE_DIMENSION_MISMATCH" in result.diagnostics


def test_optimize_penalizes_turnover() -> None:
    # Strong turnover penalty should keep weights near the previous portfolio.
    prev = (0.1, 0.4, 0.5)
    high_tc = OptimizationSpec(spec_id="s", lambda_risk=0.0, lambda_turnover=10.0)
    result = optimize(
        alpha(), covariance(), prev_weights=prev, spec=high_tc, max_single_weight=0.8
    )

    # weights stay close to prev despite alpha favoring asset 0
    assert result.weights[2] > result.weights[0]


def test_optimize_is_deterministic() -> None:
    first = optimize(alpha(), covariance(), max_single_weight=0.5, spec=spec())
    second = optimize(alpha(), covariance(), max_single_weight=0.5, spec=spec())

    assert first == second
    assert first.content_hash() == second.content_hash()


def test_rejects_empty_alpha() -> None:
    with pytest.raises(ValueError):
        optimize((), ((),), spec=spec())


def test_rejects_invalid_learning_rate() -> None:
    with pytest.raises(ValueError):
        OptimizationSpec(spec_id="s", learning_rate=1.5)


def test_rejects_negative_prev_weight() -> None:
    with pytest.raises(ValueError):
        optimize(
            alpha(),
            covariance(),
            prev_weights=(-0.1, 0.5, 0.6),
            max_single_weight=0.5,
            spec=spec(),
        )
