"""Multi-candidate false-discovery analysis (G6-005, closes G5 R1).

Wires the G5 statistics (Benjamini-Hochberg FDR, Deflated Sharpe Ratio, and
Probability of Backtest Overfitting) into one end-to-end flow over a candidate
set: a p-value vector for BH, and a strategy-return matrix for DSR/PBO.
"""

from __future__ import annotations

from dataclasses import dataclass

from quant_platform.experiments import canonical_hash
from quant_platform.validation.statistics import (
    benjamini_hochberg,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
)


@dataclass(frozen=True, slots=True)
class FalseDiscoveryReport:
    adjusted_pvalues: tuple[float, ...]
    rejected_count: int
    deflated_sharpe_ratio: float | None
    pbo: float | None
    candidate_count: int

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "false-discovery/v1",
            "adjusted_pvalues": list(self.adjusted_pvalues),
            "rejected_count": self.rejected_count,
            "deflated_sharpe_ratio": self.deflated_sharpe_ratio,
            "pbo": self.pbo,
            "candidate_count": self.candidate_count,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def run_false_discovery(
    p_values: tuple[float, ...],
    strategy_returns: tuple[tuple[float, ...], ...],
    *,
    sharpe: float | None = None,
    skew: float | None = None,
    kurtosis: float | None = None,
    n_observations: int | None = None,
    alpha: float = 0.05,
    n_splits: int = 16,
    n_combinations: int = 100,
    seed: int = 0,
) -> FalseDiscoveryReport:
    if not p_values:
        raise ValueError("p_values must not be empty")
    if any(not 0.0 <= p <= 1.0 for p in p_values):
        raise ValueError("p_values must be within [0, 1]")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be strictly between 0 and 1")

    adjusted = benjamini_hochberg(p_values)
    rejected = sum(1 for q in adjusted if q < alpha)

    dsr: float | None = None
    if (
        sharpe is not None
        and skew is not None
        and kurtosis is not None
        and n_observations is not None
    ):
        dsr = deflated_sharpe_ratio(
            sharpe,
            skew,
            kurtosis,
            n_trials=len(p_values),
            n_observations=n_observations,
        )

    pbo: float | None = None
    if len(strategy_returns) >= 2:
        pbo = probability_of_backtest_overfitting(
            strategy_returns,
            n_splits=n_splits,
            n_combinations=n_combinations,
            seed=seed,
        )

    return FalseDiscoveryReport(
        adjusted_pvalues=adjusted,
        rejected_count=rejected,
        deflated_sharpe_ratio=dsr,
        pbo=pbo,
        candidate_count=len(p_values),
    )
