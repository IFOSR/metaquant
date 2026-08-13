"""Alpha Pool contracts (G6-001).

The Alpha Pool holds promoted factors. ``AlphaPoolFactor`` records a factor's
identity, direction, universe, horizon, validation policy, out-of-sample IC,
risk-premium marker, and lifecycle state. ``AlphaPool`` is an immutable set
that resolves members by factor IR hash and fails closed on duplicates or
missing entries.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from quant_platform.experiments import canonical_hash

_VALID_MARKETS = frozenset({"CN_A", "CN_COMMODITY_FUTURES"})
_HEX_DIGITS = frozenset("0123456789abcdef")


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


def _require_ir_hash(value: str) -> None:
    if len(value) != 64 or any(ch not in _HEX_DIGITS for ch in value):
        raise ValueError("factor_ir_hash must be a 64-character hex digest")


class FactorDirection(str, Enum):
    LONG_ONLY = "LONG_ONLY"
    SHORT_ONLY = "SHORT_ONLY"
    LONG_SHORT = "LONG_SHORT"


class LifecycleState(str, Enum):
    CANDIDATE = "CANDIDATE"
    PROMOTED = "PROMOTED"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class AlphaPoolFactor:
    factor_ir_hash: str
    direction: FactorDirection
    market: str
    universe: str
    horizon: int
    policy_id: str
    risk_premium: bool
    lifecycle_state: LifecycleState
    oos_ic: float | None = None

    def __post_init__(self) -> None:
        _require_ir_hash(self.factor_ir_hash)
        if not isinstance(self.direction, FactorDirection):
            object.__setattr__(self, "direction", FactorDirection(self.direction))
        if self.market not in _VALID_MARKETS:
            raise ValueError("market must be CN_A or CN_COMMODITY_FUTURES")
        _require_identifier(self.universe, "universe")
        if self.horizon < 1:
            raise ValueError("horizon must be positive")
        _require_identifier(self.policy_id, "policy_id")
        if not isinstance(self.lifecycle_state, LifecycleState):
            object.__setattr__(
                self, "lifecycle_state", LifecycleState(self.lifecycle_state)
            )
        if self.oos_ic is not None and not math.isfinite(self.oos_ic):
            raise ValueError("oos_ic must be finite or None")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "alpha-pool-factor/v1",
            "factor_ir_hash": self.factor_ir_hash,
            "direction": self.direction.value,
            "market": self.market,
            "universe": self.universe,
            "horizon": self.horizon,
            "policy_id": self.policy_id,
            "risk_premium": self.risk_premium,
            "lifecycle_state": self.lifecycle_state.value,
            "oos_ic": self.oos_ic,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


@dataclass(frozen=True, slots=True)
class AlphaPool:
    factors: tuple[AlphaPoolFactor, ...]

    def __post_init__(self) -> None:
        hashes = [item.factor_ir_hash for item in self.factors]
        if len(set(hashes)) != len(hashes):
            raise ValueError("alpha pool factors must be unique by factor_ir_hash")

    def resolve(self, factor_ir_hash: str) -> AlphaPoolFactor:
        for item in self.factors:
            if item.factor_ir_hash == factor_ir_hash:
                return item
        raise ValueError("ALPHA_POOL_FACTOR_NOT_FOUND")

    def ir_hashes(self) -> frozenset[str]:
        return frozenset(item.factor_ir_hash for item in self.factors)

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "alpha-pool/v1",
            "factors": [item.payload() for item in self.factors],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


class AlphaPoolCatalog(Protocol):
    def resolve(self) -> AlphaPool: ...


class InMemoryAlphaPoolCatalog:
    def __init__(self, pool: AlphaPool) -> None:
        self._pool = pool

    def resolve(self) -> AlphaPool:
        return self._pool
