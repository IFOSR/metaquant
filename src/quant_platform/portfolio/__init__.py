"""Portfolio construction (G8).

Factor combination and constrained portfolio optimization. Factor weights are
estimated only on training-window IC, frozen for the next out-of-sample fold,
and normalized under deterministic constraints. The equal-weight baseline is
always available, and both factor ablation and marginal contribution are
reported.
"""

from quant_platform.portfolio.combination import (
    AblationResult,
    CombinationReport,
    CombinationSpec,
    CombinationWeights,
    FactorSignal,
    equal_weight,
    factor_ablation,
    marginal_contributions,
    mvp_combine,
)
from quant_platform.portfolio.optimizer import (
    OptimizationResult,
    OptimizationSpec,
    optimize,
)

__all__ = [
    "AblationResult",
    "CombinationReport",
    "CombinationSpec",
    "CombinationWeights",
    "FactorSignal",
    "OptimizationResult",
    "OptimizationSpec",
    "equal_weight",
    "factor_ablation",
    "marginal_contributions",
    "mvp_combine",
    "optimize",
]
