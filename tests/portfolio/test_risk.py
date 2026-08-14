from __future__ import annotations

import pytest

from quant_platform.portfolio.optimizer import OptimizationSpec, optimize


def alpha() -> tuple[float, ...]:
    return (0.10, 0.05, 0.02)


def covariance() -> tuple[tuple[float, ...], ...]:
    return (
        (0.10, 0.00, 0.00),
        (0.00, 0.08, 0.00),
        (0.00, 0.00, 0.06),
    )


def test_factor_exposure_neutrality() -> None:
    # asset 0 is long the factor, asset 1 short, asset 2 neutral;
    # a neutral portfolio must hold equal weight in assets 0 and 1.
    exposures = ((1.0,), (-1.0,), (0.0,))
    result = optimize(
        alpha(),
        covariance(),
        max_single_weight=0.6,
        exposures=exposures,
        spec=OptimizationSpec(spec_id="s", lambda_risk=0.0, lambda_turnover=0.0),
    )

    net_exposure = result.weights[0] - result.weights[1]
    assert abs(net_exposure) < 0.05


def test_exposure_defaults_to_neutral() -> None:
    exposures = ((1.0,), (1.0,), (-2.0,))
    result = optimize(
        alpha(),
        covariance(),
        max_single_weight=0.6,
        exposures=exposures,
        spec=OptimizationSpec(spec_id="s"),
    )

    # target defaults to zero: w0 + w1 - 2*w2 ~ 0
    net = result.weights[0] + result.weights[1] - 2.0 * result.weights[2]
    assert abs(net) < 0.05


def test_tracking_error_penalty_pulls_toward_benchmark() -> None:
    benchmark = (0.2, 0.3, 0.5)
    result = optimize(
        alpha(),
        covariance(),
        max_single_weight=0.6,
        benchmark_weights=benchmark,
        lambda_tracking_error=10.0,
        spec=OptimizationSpec(spec_id="s", lambda_risk=0.0, lambda_turnover=0.0),
    )

    distance = sum(abs(result.weights[i] - benchmark[i]) for i in range(3))
    # a strong tracking-error penalty keeps weights close to the benchmark
    assert distance < 0.3


def test_exposure_dimension_mismatch_rejected() -> None:
    with pytest.raises(ValueError):
        optimize(
            alpha(),
            covariance(),
            max_single_weight=0.6,
            exposures=((1.0,), (-1.0,)),
            spec=OptimizationSpec(spec_id="s"),
        )


def test_exposure_targets_mismatch_rejected() -> None:
    with pytest.raises(ValueError):
        optimize(
            alpha(),
            covariance(),
            max_single_weight=0.6,
            exposures=((1.0,), (-1.0,), (0.0,)),
            exposure_targets=(0.0, 0.0),
            spec=OptimizationSpec(spec_id="s"),
        )


def test_negative_tracking_error_rejected() -> None:
    with pytest.raises(ValueError):
        optimize(
            alpha(),
            covariance(),
            max_single_weight=0.6,
            lambda_tracking_error=-1.0,
            spec=OptimizationSpec(spec_id="s"),
        )
