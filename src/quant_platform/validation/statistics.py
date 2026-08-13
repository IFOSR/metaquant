"""False-discovery statistics (G5-004, G5-005).

Deterministic, dependency-free implementations of Benjamini-Hochberg FDR
adjustment, Deflated Sharpe Ratio (Bailey & Lopez de Prado), and Probability of
Backtest Overfitting (combinatorially symmetric cross-validation).
"""

from __future__ import annotations

import math
import random


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Standard normal quantile via Acklam's rational approximation."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    low, high = 0.02425, 1.0 - 0.02425
    if p < low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


def benjamini_hochberg(p_values: tuple[float, ...]) -> tuple[float, ...]:
    """Benjamini-Hochberg adjusted p-values (FDR q-values).

    Stable ordering; returns adjusted values in the input order.
    """
    n = len(p_values)
    if n == 0:
        return ()
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [0.0] * n
    previous = 1.0
    for rank, (original_index, p) in reversed(list(enumerate(indexed, start=1))):
        q = min(p * n / rank, previous)
        adjusted[original_index] = min(q, 1.0)
        previous = q
    return tuple(adjusted)


def deflated_sharpe_ratio(
    sharpe: float,
    skew: float,
    kurtosis: float,
    n_trials: int,
    n_observations: int,
) -> float:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado).

    The benchmark is deflated by the expected maximum Sharpe over ``n_trials``
    trials, ``sqrt(2 * ln(n_trials))``, so a Sharpe that is merely a survivor
    of many trials is not credited as skill. The result is the Probabilistic
    Sharpe Ratio against the deflated benchmark.
    """
    if n_trials < 1:
        raise ValueError("n_trials must be positive")
    if n_observations < 3:
        raise ValueError("n_observations must be at least 3")
    sr_star = math.sqrt(2.0 * math.log(n_trials))
    numerator = (sharpe - sr_star) * math.sqrt(n_observations - 1)
    denominator = math.sqrt(1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2)
    if denominator <= 0.0:
        return 0.0
    return _norm_cdf(numerator / denominator)


def probability_of_backtest_overfitting(
    returns: tuple[tuple[float, ...], ...],
    *,
    n_splits: int = 16,
    n_combinations: int = 100,
    seed: int = 0,
) -> float:
    """Probability of Backtest Overfitting via CSCV.

    ``returns`` is a matrix of strategy return series (strategies x periods).
    The periods are split into ``n_splits`` blocks; ``n_combinations`` random
    in-sample/out-of-sample partitions are drawn, and the fraction of
    partitions where the in-sample best strategy ranks below the median
    out-of-sample is returned.
    """
    n_strategies = len(returns)
    if n_strategies < 2:
        raise ValueError("PBO requires at least two strategies")
    n_periods = len(returns[0]) if n_strategies else 0
    if any(len(series) != n_periods for series in returns):
        raise ValueError("PBO return series must have equal length")
    if n_splits < 2 or n_splits % 2 != 0 or n_periods < n_splits:
        raise ValueError("n_splits must be even and not exceed the period count")

    block_size = n_periods // n_splits
    blocks = [
        [
            series[block * block_size : (block + 1) * block_size]
            for block in range(n_splits)
        ]
        for series in returns
    ]

    def _sharpe(values: list[float]) -> float:
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = math.sqrt(variance)
        return mean / std if std > 0.0 else 0.0

    rng = random.Random(seed)
    below_median = 0
    for _ in range(n_combinations):
        in_sample = set(rng.sample(range(n_splits), n_splits // 2))

        is_sharpes = [
            _sharpe(
                [
                    value
                    for i, block in enumerate(blocks[strategy])
                    if i in in_sample
                    for value in block
                ]
            )
            for strategy in range(n_strategies)
        ]
        oos_sharpes = [
            _sharpe(
                [
                    value
                    for i, block in enumerate(blocks[strategy])
                    if i not in in_sample
                    for value in block
                ]
            )
            for strategy in range(n_strategies)
        ]
        best = max(range(n_strategies), key=lambda i: is_sharpes[i])
        oos_rank = sum(1 for value in oos_sharpes if value > oos_sharpes[best])
        if oos_rank >= n_strategies / 2:
            below_median += 1

    return below_median / n_combinations
