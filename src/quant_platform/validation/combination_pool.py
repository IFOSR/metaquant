"""Combination pool contracts (G7-004).

A ``CombinationPool`` is the immutable set of factors that passed Gate 5 and are
eligible for factor combination. Membership is keyed by factor IR hash and
fails closed on duplicates or missing entries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from quant_platform.experiments import canonical_hash
from quant_platform.validation.alpha_pool import FactorDirection
from quant_platform.validation.contracts import _require_aware

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PromotedFactor:
    factor_ir_hash: str
    market: str
    direction: FactorDirection
    promotion_evidence_hash: str
    promoted_at: datetime

    def __post_init__(self) -> None:
        if not _HASH_RE.fullmatch(self.factor_ir_hash):
            raise ValueError("factor_ir_hash must be a 64-char hex digest")
        if self.market not in {"CN_A", "CN_COMMODITY_FUTURES"}:
            raise ValueError("market must be CN_A or CN_COMMODITY_FUTURES")
        if not isinstance(self.direction, FactorDirection):
            object.__setattr__(self, "direction", FactorDirection(self.direction))
        if not _HASH_RE.fullmatch(self.promotion_evidence_hash):
            raise ValueError("promotion_evidence_hash must be a 64-char hex digest")
        _require_aware(self.promoted_at, "promoted_at")


@dataclass(frozen=True, slots=True)
class CombinationPool:
    factors: tuple[PromotedFactor, ...]

    def __post_init__(self) -> None:
        keys = [item.factor_ir_hash for item in self.factors]
        if len(set(keys)) != len(keys):
            raise ValueError("combination pool factor hashes must be unique")

    def add(self, factor: PromotedFactor) -> CombinationPool:
        if self.contains(factor.factor_ir_hash):
            raise ValueError("FACTOR_ALREADY_IN_POOL")
        return CombinationPool(self.factors + (factor,))

    def contains(self, factor_ir_hash: str) -> bool:
        return any(item.factor_ir_hash == factor_ir_hash for item in self.factors)

    def resolve(self, factor_ir_hash: str) -> PromotedFactor:
        for item in self.factors:
            if item.factor_ir_hash == factor_ir_hash:
                return item
        raise ValueError("FACTOR_NOT_IN_POOL")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "combination-pool/v1",
            "factors": [
                {
                    "factor_ir_hash": item.factor_ir_hash,
                    "market": item.market,
                    "direction": item.direction.value,
                    "promotion_evidence_hash": item.promotion_evidence_hash,
                    "promoted_at": item.promoted_at.isoformat(),
                }
                for item in self.factors
            ],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())
