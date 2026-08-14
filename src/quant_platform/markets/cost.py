"""Declarative trading cost models (G8, Gate 6).

Cost models are versioned, immutable, per-market data. ``CN_A`` uses an
equity model (commission, stamp duty, transfer fee, slippage, impact,
funding/borrow); ``CN_COMMODITY_FUTURES`` uses a futures model (fee, slippage,
impact, margin, funding). All arithmetic is deterministic floating point with
a fixed operation order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quant_platform.experiments import canonical_hash
from quant_platform.markets.cn_a import OrderSide
from quant_platform.markets.contracts import MarketId

_VALID_MARKETS = frozenset({MarketId.CN_A, MarketId.CN_COMMODITY_FUTURES})
_BPS = 10_000.0


def _require_rate(value: float, name: str, upper: float) -> None:
    if not 0.0 <= value <= upper:
        raise ValueError(f"{name} must be within [0, {upper}]")


@dataclass(frozen=True, slots=True)
class EquityCostModel:
    model_id: str
    market: MarketId
    commission_rate: float
    minimum_commission: float
    stamp_duty_rate: float
    transfer_fee_rate: float
    slippage_bps: float
    impact_bps_per_adv: float
    funding_rate_daily: float
    borrow_rate_daily: float

    def __post_init__(self) -> None:
        if not self.model_id or self.model_id.strip() != self.model_id:
            raise ValueError("model_id must be a non-empty normalized identifier")
        if self.market is not MarketId.CN_A:
            raise ValueError("EquityCostModel requires market CN_A")
        _require_rate(self.commission_rate, "commission_rate", 0.1)
        _require_rate(self.minimum_commission, "minimum_commission", 1000.0)
        _require_rate(self.stamp_duty_rate, "stamp_duty_rate", 0.1)
        _require_rate(self.transfer_fee_rate, "transfer_fee_rate", 0.1)
        _require_rate(self.slippage_bps, "slippage_bps", 1000.0)
        _require_rate(self.impact_bps_per_adv, "impact_bps_per_adv", 1000.0)
        _require_rate(self.funding_rate_daily, "funding_rate_daily", 1.0)
        _require_rate(self.borrow_rate_daily, "borrow_rate_daily", 1.0)

    def single_side_cost(self, side: OrderSide, notional: float) -> float:
        if notional < 0:
            raise ValueError("notional must be non-negative")
        commission = max(notional * self.commission_rate, self.minimum_commission)
        stamp = notional * self.stamp_duty_rate if side is OrderSide.SELL else 0.0
        transfer = notional * self.transfer_fee_rate
        slippage = notional * self.slippage_bps / _BPS
        return commission + stamp + transfer + slippage

    def impact_cost(self, notional: float, adv: float) -> float:
        if notional < 0:
            raise ValueError("notional must be non-negative")
        if adv <= 0:
            raise ValueError("adv must be positive")
        participation = notional / adv
        return notional * (participation * self.impact_bps_per_adv) / _BPS

    def round_trip_cost(self, notional: float, adv: float | None = None) -> float:
        base = self.single_side_cost(OrderSide.BUY, notional) + self.single_side_cost(
            OrderSide.SELL, notional
        )
        if adv is None:
            return base
        return base + 2.0 * self.impact_cost(notional, adv)

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "cost-model/v1",
            "kind": "equity",
            "model_id": self.model_id,
            "market": self.market.value,
            "commission_rate": self.commission_rate,
            "minimum_commission": self.minimum_commission,
            "stamp_duty_rate": self.stamp_duty_rate,
            "transfer_fee_rate": self.transfer_fee_rate,
            "slippage_bps": self.slippage_bps,
            "impact_bps_per_adv": self.impact_bps_per_adv,
            "funding_rate_daily": self.funding_rate_daily,
            "borrow_rate_daily": self.borrow_rate_daily,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


@dataclass(frozen=True, slots=True)
class FuturesCostModel:
    model_id: str
    market: MarketId
    fee_rate: float
    slippage_bps: float
    impact_bps_per_adv: float
    margin_rate: float
    funding_rate_daily: float

    def __post_init__(self) -> None:
        if not self.model_id or self.model_id.strip() != self.model_id:
            raise ValueError("model_id must be a non-empty normalized identifier")
        if self.market is not MarketId.CN_COMMODITY_FUTURES:
            raise ValueError("FuturesCostModel requires market CN_COMMODITY_FUTURES")
        _require_rate(self.fee_rate, "fee_rate", 0.1)
        _require_rate(self.slippage_bps, "slippage_bps", 1000.0)
        _require_rate(self.impact_bps_per_adv, "impact_bps_per_adv", 1000.0)
        _require_rate(self.margin_rate, "margin_rate", 1.0)
        _require_rate(self.funding_rate_daily, "funding_rate_daily", 1.0)

    def single_side_cost(self, notional: float) -> float:
        if notional < 0:
            raise ValueError("notional must be non-negative")
        return notional * self.fee_rate + notional * self.slippage_bps / _BPS

    def impact_cost(self, notional: float, adv: float) -> float:
        if notional < 0:
            raise ValueError("notional must be non-negative")
        if adv <= 0:
            raise ValueError("adv must be positive")
        participation = notional / adv
        return notional * (participation * self.impact_bps_per_adv) / _BPS

    def round_trip_cost(self, notional: float, adv: float | None = None) -> float:
        base = 2.0 * self.single_side_cost(notional)
        if adv is None:
            return base
        return base + 2.0 * self.impact_cost(notional, adv)

    def margin_requirement(self, notional: float) -> float:
        if notional < 0:
            raise ValueError("notional must be non-negative")
        return notional * self.margin_rate

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "cost-model/v1",
            "kind": "futures",
            "model_id": self.model_id,
            "market": self.market.value,
            "fee_rate": self.fee_rate,
            "slippage_bps": self.slippage_bps,
            "impact_bps_per_adv": self.impact_bps_per_adv,
            "margin_rate": self.margin_rate,
            "funding_rate_daily": self.funding_rate_daily,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


CostModel = EquityCostModel | FuturesCostModel


class CostModelCatalog(Protocol):
    def resolve(self, model_id: str) -> CostModel: ...


class InMemoryCostModelCatalog:
    def __init__(self, models: tuple[CostModel, ...]) -> None:
        self._models = {str(item.model_id): item for item in models}
        if len(self._models) != len(models):
            raise ValueError("cost model ids must be unique")

    def resolve(self, model_id: str) -> CostModel:
        try:
            return self._models[model_id]
        except KeyError as exc:
            raise ValueError("COST_MODEL_NOT_REGISTERED") from exc
