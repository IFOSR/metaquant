"""Strategy specification contracts (G10-001).

A ``StrategySpec`` declares the market, universe, factor weights, leverage,
risk limits, cost model, validation policy, and roll policy for a strategy. It
is immutable and content-addressed, and is the single source consumed by both
formal backtesting and (later) paper/live execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quant_platform.experiments import canonical_hash

_VALID_MARKETS = frozenset({"CN_A", "CN_COMMODITY_FUTURES"})
_HEX_DIGITS = frozenset("0123456789abcdef")


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


def _require_ir_hash(value: str) -> None:
    if len(value) != 64 or any(ch not in _HEX_DIGITS for ch in value):
        raise ValueError("factor_ir_hash must be a 64-character hex digest")


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_single_weight: Decimal
    max_holdings: int
    turnover_budget: Decimal
    tracking_error: Decimal | None = None

    def __post_init__(self) -> None:
        if not Decimal("0") < self.max_single_weight <= Decimal("1"):
            raise ValueError("max_single_weight must be within (0, 1]")
        if self.max_holdings < 1:
            raise ValueError("max_holdings must be positive")
        if self.turnover_budget < Decimal("0"):
            raise ValueError("turnover_budget must be non-negative")
        if self.tracking_error is not None and self.tracking_error <= Decimal("0"):
            raise ValueError("tracking_error must be positive when provided")

    def payload(self) -> dict[str, object]:
        return {
            "max_single_weight": str(self.max_single_weight),
            "max_holdings": self.max_holdings,
            "turnover_budget": str(self.turnover_budget),
            "tracking_error": (
                str(self.tracking_error) if self.tracking_error is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class StrategySpec:
    strategy_id: str
    market: str
    universe_ref: str
    frequency: str
    factor_weights: tuple[tuple[str, Decimal], ...]
    leverage: Decimal
    risk_limits: RiskLimits
    cost_model_ref: str
    validation_policy_ref: str
    roll_policy_ref: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.strategy_id, "strategy_id")
        if self.market not in _VALID_MARKETS:
            raise ValueError("market must be CN_A or CN_COMMODITY_FUTURES")
        _require_identifier(self.universe_ref, "universe_ref")
        if self.frequency != "1d":
            raise ValueError("frequency must be 1d")
        if not self.factor_weights:
            raise ValueError("factor_weights must not be empty")
        hashes = [item[0] for item in self.factor_weights]
        if len(set(hashes)) != len(hashes):
            raise ValueError("factor_weights must be unique per factor_ir_hash")
        for factor_ir_hash, weight in self.factor_weights:
            _require_ir_hash(factor_ir_hash)
            if weight <= Decimal("0") or not weight.is_finite():
                raise ValueError("factor weights must be positive finite")
        total = sum(weight for _, weight in self.factor_weights)
        if not (Decimal("0.99") < total < Decimal("1.01")):
            raise ValueError("factor weights must sum to approximately one")
        if self.leverage <= Decimal("0"):
            raise ValueError("leverage must be positive")
        _require_identifier(self.cost_model_ref, "cost_model_ref")
        _require_identifier(self.validation_policy_ref, "validation_policy_ref")
        if self.market == "CN_COMMODITY_FUTURES" and self.roll_policy_ref is None:
            raise ValueError("commodity futures strategies require a roll_policy_ref")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "strategy-spec/v1",
            "strategy_id": self.strategy_id,
            "market": self.market,
            "universe_ref": self.universe_ref,
            "frequency": self.frequency,
            "factor_weights": [
                {"factor_ir_hash": item[0], "weight": str(item[1])}
                for item in self.factor_weights
            ],
            "leverage": str(self.leverage),
            "risk_limits": self.risk_limits.payload(),
            "cost_model_ref": self.cost_model_ref,
            "validation_policy_ref": self.validation_policy_ref,
            "roll_policy_ref": self.roll_policy_ref,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())
