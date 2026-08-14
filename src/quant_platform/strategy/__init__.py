"""Strategy specification and package contracts (G10)."""

from quant_platform.strategy.package import (
    DataManifest,
    StrategyPackage,
    build_package,
    verify_package,
)
from quant_platform.strategy.spec import (
    RiskLimits,
    StrategySpec,
)

__all__ = [
    "DataManifest",
    "RiskLimits",
    "StrategyPackage",
    "StrategySpec",
    "build_package",
    "verify_package",
]
