"""Capacity model contracts (G6-004).

A declarative ``CapacityModel`` (ADV participation cap, impact coefficient,
margin rate, limit-up/down and suspension exclusions) drives a deterministic
``run_capacity`` that returns per-name capacity and the AUM capacity curve at
participation steps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from quant_platform.data_gateway.models import FrozenSnapshot
from quant_platform.experiments import canonical_hash

_VALID_MARKETS = frozenset({"CN_A", "CN_COMMODITY_FUTURES"})
_ADV_FIELD = "market.eod.adv"
_TRADABLE_FIELD = "market.eod.tradable"


@dataclass(frozen=True, slots=True)
class CapacityModel:
    market: str
    max_adv_participation: float
    impact_coefficient: float
    margin_rate: float
    exclude_limit_up_down: bool
    exclude_suspended: bool

    def __post_init__(self) -> None:
        if self.market not in _VALID_MARKETS:
            raise ValueError("market must be CN_A or CN_COMMODITY_FUTURES")
        if not 0.0 < self.max_adv_participation <= 1.0:
            raise ValueError("max_adv_participation must be within (0, 1]")
        if self.impact_coefficient < 0.0:
            raise ValueError("impact_coefficient must be non-negative")
        if not 0.0 < self.margin_rate <= 1.0:
            raise ValueError("margin_rate must be within (0, 1]")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "capacity-model/v1",
            "market": self.market,
            "max_adv_participation": self.max_adv_participation,
            "impact_coefficient": self.impact_coefficient,
            "margin_rate": self.margin_rate,
            "exclude_limit_up_down": self.exclude_limit_up_down,
            "exclude_suspended": self.exclude_suspended,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


@dataclass(frozen=True, slots=True)
class NameCapacity:
    instrument_id: str
    adv: float
    tradable: bool
    capacity: float

    def payload(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "adv": self.adv,
            "tradable": self.tradable,
            "capacity": self.capacity,
        }


@dataclass(frozen=True, slots=True)
class AumPoint:
    participation: float
    aum: float
    cost_per_unit: float

    def payload(self) -> dict[str, object]:
        return {
            "participation": self.participation,
            "aum": self.aum,
            "cost_per_unit": self.cost_per_unit,
        }


@dataclass(frozen=True, slots=True)
class CapacityReport:
    per_name: tuple[NameCapacity, ...]
    aum_curve: tuple[AumPoint, ...]
    total_capacity: float
    tradable_count: int

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "capacity/v1",
            "per_name": [item.payload() for item in self.per_name],
            "aum_curve": [item.payload() for item in self.aum_curve],
            "total_capacity": self.total_capacity,
            "tradable_count": self.tradable_count,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def run_capacity(
    adv: dict[str, float],
    tradable: dict[str, bool],
    model: CapacityModel,
    *,
    participation_steps: tuple[float, ...] = (0.005, 0.01, 0.02, 0.05, 0.1),
) -> CapacityReport:
    if not participation_steps:
        raise ValueError("participation_steps must not be empty")
    if any(p <= 0.0 for p in participation_steps):
        raise ValueError("participation_steps must be positive")
    if any(
        second <= first
        for first, second in zip(
            participation_steps, participation_steps[1:], strict=False
        )
    ):
        raise ValueError("participation_steps must be strictly increasing")
    if any(value <= 0.0 for value in adv.values()):
        raise ValueError("adv must be positive")

    instruments = sorted(adv.keys())
    per_name = tuple(
        NameCapacity(
            instrument_id=instrument,
            adv=adv[instrument],
            tradable=tradable.get(instrument, False),
            capacity=(
                adv[instrument] * model.max_adv_participation
                if tradable.get(instrument, False)
                else 0.0
            ),
        )
        for instrument in instruments
    )
    aum_curve = tuple(
        AumPoint(
            participation=participation,
            aum=sum(
                adv[instrument] * participation
                for instrument in instruments
                if tradable.get(instrument, False)
            ),
            cost_per_unit=model.impact_coefficient * math.sqrt(participation),
        )
        for participation in participation_steps
    )
    total_capacity = sum(
        adv[instrument] * model.max_adv_participation
        for instrument in instruments
        if tradable.get(instrument, False)
    )
    tradable_count = sum(
        1 for instrument in instruments if tradable.get(instrument, False)
    )
    return CapacityReport(
        per_name=per_name,
        aum_curve=aum_curve,
        total_capacity=total_capacity,
        tradable_count=tradable_count,
    )


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    if isinstance(value, int | float):
        return value != 0
    return bool(value)


def extract_tradability(
    snapshot: FrozenSnapshot,
    *,
    adv_field: str = _ADV_FIELD,
    tradable_field: str = _TRADABLE_FIELD,
) -> tuple[dict[str, float], dict[str, bool]]:
    """Extract per-instrument ADV and tradability from a frozen snapshot.

    These are the market-data inputs to ``run_capacity``. The latest (highest
    event time) observation wins per instrument; non-numeric or non-positive ADV
    values are skipped so capacity only considers known, liquid names.
    """
    adv: dict[str, float] = {}
    adv_time: dict[str, datetime] = {}
    tradable: dict[str, bool] = {}
    tradable_time: dict[str, datetime] = {}

    for row in snapshot.rows:
        if row.field == adv_field:
            if isinstance(row.value, bool) or not isinstance(row.value, int | float):
                continue
            value = float(row.value)
            if not math.isfinite(value) or value <= 0.0:
                continue
            current = adv_time.get(row.instrument_id)
            if current is None or row.event_time >= current:
                adv[row.instrument_id] = value
                adv_time[row.instrument_id] = row.event_time
        elif row.field == tradable_field:
            current = tradable_time.get(row.instrument_id)
            if current is None or row.event_time >= current:
                tradable[row.instrument_id] = _to_bool(row.value)
                tradable_time[row.instrument_id] = row.event_time

    return adv, tradable
