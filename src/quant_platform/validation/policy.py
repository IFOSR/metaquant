"""Validation policy contracts (G4-002).

A ``ValidationPolicy`` is an immutable, versioned, per-market set of factor
validation thresholds. Thresholds are data, not code, and ``CN_A`` and
``CN_COMMODITY_FUTURES`` use distinct policies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast

from quant_platform.experiments import canonical_hash

_VALID_MARKETS = frozenset({"CN_A", "CN_COMMODITY_FUTURES"})
_VALID_HORIZONS = frozenset({1, 5, 10, 20, 60})


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


class ICSign(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    ANY = "ANY"


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    policy_id: str
    market: str
    min_coverage: float
    min_observations: int
    max_constant_ratio: float
    ic_sign: ICSign
    min_icir: float
    min_nw_t: float
    quantile_count: int = 5
    decay_horizons: tuple[int, ...] = (1, 5, 10, 20, 60)

    def __post_init__(self) -> None:
        _require_identifier(self.policy_id, "policy_id")
        if self.market not in _VALID_MARKETS:
            raise ValueError("market must be CN_A or CN_COMMODITY_FUTURES")
        if not 0.0 <= self.min_coverage <= 1.0:
            raise ValueError("min_coverage must be within [0, 1]")
        if self.min_observations < 1:
            raise ValueError("min_observations must be positive")
        if not 0.0 <= self.max_constant_ratio <= 1.0:
            raise ValueError("max_constant_ratio must be within [0, 1]")
        if not isinstance(self.ic_sign, ICSign):
            object.__setattr__(self, "ic_sign", ICSign(self.ic_sign))
        if self.min_icir < 0:
            raise ValueError("min_icir must be non-negative")
        if self.min_nw_t < 0:
            raise ValueError("min_nw_t must be non-negative")
        if self.quantile_count < 2:
            raise ValueError("quantile_count must be at least 2")
        horizons = tuple(self.decay_horizons)
        object.__setattr__(self, "decay_horizons", horizons)
        if not horizons:
            raise ValueError("decay_horizons must not be empty")
        if len(set(horizons)) != len(horizons):
            raise ValueError("decay_horizons must be unique")
        if any(h not in _VALID_HORIZONS for h in horizons):
            raise ValueError("decay_horizons must be a subset of 1/5/10/20/60")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "validation-policy/v1",
            "policy_id": self.policy_id,
            "market": self.market,
            "min_coverage": self.min_coverage,
            "min_observations": self.min_observations,
            "max_constant_ratio": self.max_constant_ratio,
            "ic_sign": self.ic_sign.value,
            "min_icir": self.min_icir,
            "min_nw_t": self.min_nw_t,
            "quantile_count": self.quantile_count,
            "decay_horizons": list(self.decay_horizons),
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


class ValidationPolicyCatalog(Protocol):
    def resolve(self, policy_id: str) -> ValidationPolicy: ...


class InMemoryValidationPolicyCatalog:
    def __init__(self, policies: tuple[ValidationPolicy, ...]) -> None:
        self._policies = {str(item.policy_id): item for item in policies}
        if len(self._policies) != len(policies):
            raise ValueError("validation policy ids must be unique")

    def resolve(self, policy_id: str) -> ValidationPolicy:
        try:
            return self._policies[policy_id]
        except KeyError as exc:
            raise ValueError("VALIDATION_POLICY_NOT_REGISTERED") from exc


class JsonValidationPolicyCatalog(InMemoryValidationPolicyCatalog):
    @classmethod
    def from_path(cls, path: Path) -> JsonValidationPolicyCatalog:
        document = json.loads(path.read_text())
        if not isinstance(document, list):
            raise ValueError("validation policy catalog must be a JSON array")
        policies = tuple(
            ValidationPolicy(
                policy_id=str(item["policy_id"]),
                market=str(item["market"]),
                min_coverage=float(item["min_coverage"]),
                min_observations=int(item["min_observations"]),
                max_constant_ratio=float(item["max_constant_ratio"]),
                ic_sign=ICSign(str(item["ic_sign"])),
                min_icir=float(item["min_icir"]),
                min_nw_t=float(item["min_nw_t"]),
                quantile_count=int(item.get("quantile_count", 5)),
                decay_horizons=tuple(
                    int(h) for h in item.get("decay_horizons", [1, 5, 10, 20, 60])
                ),
            )
            for item in cast(list[dict[str, Any]], document)
        )
        return cls(policies)
