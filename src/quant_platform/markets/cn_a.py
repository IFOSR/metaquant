from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class FillCertainty(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class TradabilityAssessment:
    certainty: FillCertainty
    reason: str


@dataclass(frozen=True, slots=True)
class PositionLot:
    quantity: int
    acquired_on: date

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("position lot quantity must be positive")


@dataclass(frozen=True, slots=True)
class ASharePosition:
    lots: tuple[PositionLot, ...]

    def sellable_quantity(self, trade_date: date) -> int:
        return sum(lot.quantity for lot in self.lots if lot.acquired_on < trade_date)

    def sell(self, quantity: int, trade_date: date) -> ASharePosition:
        if quantity <= 0:
            raise ValueError("sale quantity must be positive")
        if quantity > self.sellable_quantity(trade_date):
            raise ValueError("sale exceeds T+1 sellable quantity")

        remaining = quantity
        retained: list[PositionLot] = []
        for lot in self.lots:
            if remaining and lot.acquired_on < trade_date:
                consumed = min(lot.quantity, remaining)
                remaining -= consumed
                if consumed < lot.quantity:
                    retained.append(replace(lot, quantity=lot.quantity - consumed))
            else:
                retained.append(lot)
        return ASharePosition(tuple(retained))


@dataclass(frozen=True, slots=True)
class PriceLimitRule:
    percentage: Decimal
    tick_size: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") < self.percentage < Decimal("1"):
            raise ValueError("price-limit percentage must be between zero and one")
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")

    def band(self, basis_price: Decimal) -> tuple[Decimal, Decimal]:
        if basis_price <= 0:
            raise ValueError("basis_price must be positive")
        lower = self._round_to_tick(basis_price * (1 - self.percentage))
        upper = self._round_to_tick(basis_price * (1 + self.percentage))
        return lower, upper

    def _round_to_tick(self, value: Decimal) -> Decimal:
        ticks = (value / self.tick_size).quantize(Decimal("1"), ROUND_HALF_UP)
        return (ticks * self.tick_size).quantize(self.tick_size)


@dataclass(frozen=True, slots=True)
class AShareDailyState:
    halted: bool
    volume: int
    high: Decimal
    low: Decimal
    upper_limit: Decimal
    lower_limit: Decimal
    intraday_limit_opened: bool = False

    def __post_init__(self) -> None:
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.high < self.low:
            raise ValueError("high must not be below low")
        if self.upper_limit <= self.lower_limit:
            raise ValueError("upper_limit must exceed lower_limit")

    def assess(self, side: OrderSide) -> TradabilityAssessment:
        if self.halted:
            return TradabilityAssessment(FillCertainty.BLOCKED, "trading_halt")
        if self.volume == 0:
            return TradabilityAssessment(FillCertainty.BLOCKED, "no_volume")
        if (
            side is OrderSide.BUY
            and self.high == self.low == self.upper_limit
            and not self.intraday_limit_opened
        ):
            return TradabilityAssessment(
                FillCertainty.BLOCKED,
                "locked_upper_limit",
            )
        if (
            side is OrderSide.SELL
            and self.high == self.low == self.lower_limit
            and not self.intraday_limit_opened
        ):
            return TradabilityAssessment(
                FillCertainty.BLOCKED,
                "locked_lower_limit",
            )
        return TradabilityAssessment(FillCertainty.ELIGIBLE, "tradable")


class SecurityStatus(StrEnum):
    NORMAL = "NORMAL"
    ST = "ST"
    SUSPENDED = "SUSPENDED"
    DELISTED = "DELISTED"


@dataclass(frozen=True, slots=True)
class SecurityStatusEvent:
    status: SecurityStatus
    announced_at: datetime
    effective_from: date
    effective_to: date | None = None

    def __post_init__(self) -> None:
        _require_aware(self.announced_at, "announced_at")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")


def security_status_as_of(
    events: tuple[SecurityStatusEvent, ...],
    trade_date: date,
    decision_at: datetime,
) -> SecurityStatus:
    _require_aware(decision_at, "decision_at")
    visible = (
        event
        for event in events
        if event.announced_at <= decision_at
        and event.effective_from <= trade_date
        and (event.effective_to is None or trade_date < event.effective_to)
    )
    latest = max(
        visible,
        key=lambda event: (event.effective_from, event.announced_at),
        default=None,
    )
    return SecurityStatus.NORMAL if latest is None else latest.status


@dataclass(frozen=True, slots=True)
class MembershipEvent:
    index_id: str
    instrument_id: str
    announced_at: datetime
    effective_from: date
    effective_to: date | None

    def __post_init__(self) -> None:
        if not self.index_id or not self.instrument_id:
            raise ValueError("membership identifiers must be non-empty")
        _require_aware(self.announced_at, "announced_at")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")


def membership_as_of(
    events: tuple[MembershipEvent, ...],
    index_id: str,
    instrument_id: str,
    trade_date: date,
    decision_at: datetime,
) -> bool:
    _require_aware(decision_at, "decision_at")
    return any(
        event.index_id == index_id
        and event.instrument_id == instrument_id
        and event.announced_at <= decision_at
        and event.effective_from <= trade_date
        and (event.effective_to is None or trade_date < event.effective_to)
        for event in events
    )


@dataclass(frozen=True, slots=True)
class CashDividend:
    record_date: date
    ex_date: date
    payable_date: date
    cash_per_share: Decimal

    def __post_init__(self) -> None:
        if not self.record_date <= self.ex_date <= self.payable_date:
            raise ValueError("cash-dividend dates must be chronological")
        if self.cash_per_share < 0:
            raise ValueError("cash_per_share must be non-negative")


@dataclass(frozen=True, slots=True)
class SplitAction:
    record_date: date
    ex_date: date
    ratio: Decimal

    def __post_init__(self) -> None:
        if self.ex_date < self.record_date:
            raise ValueError("split ex_date must not precede record_date")
        if self.ratio <= 0:
            raise ValueError("split ratio must be positive")


type CorporateAction = CashDividend | SplitAction


@dataclass(frozen=True, slots=True)
class CorporateActionLedger:
    quantity: int
    cash: Decimal
    cost_basis_per_share: Decimal

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("quantity must be non-negative")
        if self.cost_basis_per_share < 0:
            raise ValueError("cost_basis_per_share must be non-negative")

    def apply(
        self,
        action: CorporateAction,
        as_of: date,
    ) -> CorporateActionLedger:
        if isinstance(action, CashDividend):
            if as_of < action.payable_date:
                return self
            return replace(
                self,
                cash=self.cash + Decimal(self.quantity) * action.cash_per_share,
            )

        if as_of < action.ex_date:
            return self
        exact_quantity = Decimal(self.quantity) * action.ratio
        quantity = int(exact_quantity)
        if Decimal(quantity) != exact_quantity:
            raise ValueError("split produces a fractional share quantity")
        return replace(
            self,
            quantity=quantity,
            cost_basis_per_share=self.cost_basis_per_share / action.ratio,
        )


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
