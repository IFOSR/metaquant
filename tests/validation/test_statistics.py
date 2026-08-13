from __future__ import annotations

import random

import pytest

from quant_platform.validation.statistics import (
    benjamini_hochberg,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
)


def test_benjamini_hochberg_golden_fixture() -> None:
    adjusted = benjamini_hochberg((0.01, 0.04, 0.03, 0.005))

    assert adjusted == pytest.approx((0.02, 0.04, 0.04, 0.02))


def test_benjamini_hochberg_empty_input() -> None:
    assert benjamini_hochberg(()) == ()


def test_benjamini_hochberg_never_decreases() -> None:
    raw = (0.5, 0.2, 0.1, 0.9, 0.3)

    adjusted = benjamini_hochberg(raw)

    assert all(q >= p for p, q in zip(raw, adjusted, strict=True))


def test_deflated_sharpe_ratio_rewards_strong_signal() -> None:
    strong = deflated_sharpe_ratio(
        sharpe=2.0, skew=0.0, kurtosis=3.0, n_trials=1, n_observations=100
    )
    weak = deflated_sharpe_ratio(
        sharpe=0.1, skew=0.0, kurtosis=3.0, n_trials=1000, n_observations=100
    )

    assert strong > 0.95
    assert weak < 0.05


def test_deflated_sharpe_ratio_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(1.0, 0.0, 3.0, n_trials=0, n_observations=100)
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(1.0, 0.0, 3.0, n_trials=1, n_observations=2)


def _noise_returns() -> tuple[tuple[float, ...], ...]:
    rng = random.Random(42)
    return tuple(tuple(rng.gauss(0.0, 0.01) for _ in range(160)) for _ in range(4))


def _signal_plus_noise_returns() -> tuple[tuple[float, ...], ...]:
    rng = random.Random(42)
    signal = tuple(0.002 + rng.gauss(0.0, 0.01) for _ in range(160))
    noise = tuple(tuple(rng.gauss(0.0, 0.01) for _ in range(160)) for _ in range(3))
    return (signal, *noise)


def test_pbo_is_deterministic() -> None:
    returns = _noise_returns()

    first = probability_of_backtest_overfitting(
        returns, n_splits=8, n_combinations=50, seed=7
    )
    second = probability_of_backtest_overfitting(
        returns, n_splits=8, n_combinations=50, seed=7
    )

    assert first == second


def test_pbo_lower_for_signal_than_noise() -> None:
    noise = probability_of_backtest_overfitting(
        _noise_returns(), n_splits=8, n_combinations=50, seed=1
    )
    signal = probability_of_backtest_overfitting(
        _signal_plus_noise_returns(), n_splits=8, n_combinations=50, seed=1
    )

    assert 0.0 <= noise <= 1.0
    assert 0.0 <= signal <= 1.0
    assert signal < noise


def test_pbo_rejects_invalid_returns() -> None:
    returns: tuple[tuple[float, ...], ...] = ((1.0, 2.0, 3.0),)
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting(returns)
