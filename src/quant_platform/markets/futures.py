from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType


class CloseOffset(StrEnum):
    CLOSE_TODAY = "CLOSE_TODAY"
    CLOSE_YESTERDAY = "CLOSE_YESTERDAY"


@dataclass(frozen=True, slots=True)
class FeeRate:
    per_lot: Decimal = Decimal("0")
    ad_valorem: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.per_lot < 0 or self.ad_valorem < 0:
            raise ValueError("fee rates must be non-negative")

    def calculate(
        self,
        quantity: int,
        price: Decimal,
        multiplier: Decimal,
    ) -> Decimal:
        if quantity < 0 or price < 0 or multiplier <= 0:
            raise ValueError("fee inputs must be non-negative")
        lots = Decimal(quantity)
        return self.per_lot * lots + self.ad_valorem * price * multiplier * lots


@dataclass(frozen=True, slots=True)
class FeeSchedule:
    rates: Mapping[CloseOffset, FeeRate]

    def __post_init__(self) -> None:
        copied = dict(self.rates)
        missing = set(CloseOffset) - set(copied)
        if missing:
            names = ", ".join(sorted(offset.value for offset in missing))
            raise ValueError(f"missing fee offsets: {names}")
        object.__setattr__(self, "rates", MappingProxyType(copied))

    def calculate(
        self,
        offset: CloseOffset,
        quantity: int,
        price: Decimal,
        multiplier: Decimal,
    ) -> Decimal:
        return self.rates[offset].calculate(quantity, price, multiplier)


@dataclass(frozen=True, slots=True)
class MarginSchedule:
    exchange_rate: Decimal
    broker_rate: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.exchange_rate <= Decimal("1"):
            raise ValueError("exchange margin rate must be between zero and one")
        if not Decimal("0") <= self.broker_rate <= Decimal("1"):
            raise ValueError("broker margin rate must be between zero and one")
        if self.broker_rate < self.exchange_rate:
            raise ValueError("broker margin may not be below exchange minimum")

    def required_margin(
        self,
        settlement_price: Decimal,
        multiplier: Decimal,
        quantity: int,
    ) -> Decimal:
        if settlement_price < 0 or multiplier <= 0 or quantity < 0:
            raise ValueError("margin inputs must be non-negative")
        return settlement_price * multiplier * Decimal(quantity) * self.broker_rate


@dataclass(frozen=True, slots=True)
class FuturesPosition:
    today_quantity: int
    yesterday_quantity: int

    def __post_init__(self) -> None:
        if self.today_quantity < 0 or self.yesterday_quantity < 0:
            raise ValueError("position quantities must be non-negative")

    def close(self, quantity: int, offset: CloseOffset) -> FuturesPosition:
        if quantity <= 0:
            raise ValueError("close quantity must be positive")
        if offset is CloseOffset.CLOSE_TODAY:
            if quantity > self.today_quantity:
                raise ValueError("close-today exceeds today position")
            return FuturesPosition(
                today_quantity=self.today_quantity - quantity,
                yesterday_quantity=self.yesterday_quantity,
            )
        if quantity > self.yesterday_quantity:
            raise ValueError("close-yesterday exceeds yesterday position")
        return FuturesPosition(
            today_quantity=self.today_quantity,
            yesterday_quantity=self.yesterday_quantity - quantity,
        )


@dataclass(frozen=True, slots=True)
class SettlementInput:
    previous_quantity: int
    previous_settlement: Decimal
    opened_quantity: int
    opened_price: Decimal
    settlement_price: Decimal
    multiplier: Decimal
    fees: Decimal

    def __post_init__(self) -> None:
        if self.previous_quantity < 0 or self.opened_quantity < 0:
            raise ValueError("settlement quantities must be non-negative")
        if (
            self.previous_settlement < 0
            or self.opened_price < 0
            or self.settlement_price < 0
            or self.fees < 0
        ):
            raise ValueError("settlement prices and fees must be non-negative")
        if self.multiplier <= 0:
            raise ValueError("contract multiplier must be positive")


@dataclass(frozen=True, slots=True)
class SettlementResult:
    mark_to_market: Decimal
    ending_quantity: int


def settle(inputs: SettlementInput) -> SettlementResult:
    previous_pnl = (
        (inputs.settlement_price - inputs.previous_settlement)
        * inputs.multiplier
        * Decimal(inputs.previous_quantity)
    )
    opened_pnl = (
        (inputs.settlement_price - inputs.opened_price)
        * inputs.multiplier
        * Decimal(inputs.opened_quantity)
    )
    return SettlementResult(
        mark_to_market=previous_pnl + opened_pnl - inputs.fees,
        ending_quantity=inputs.previous_quantity + inputs.opened_quantity,
    )


@dataclass(frozen=True, slots=True)
class DeliveryPolicy:
    force_exit_date: date
    delivery_allowed: bool

    def may_open(self, as_of: date) -> bool:
        return self.delivery_allowed or as_of < self.force_exit_date

    def must_exit(self, as_of: date) -> bool:
        return not self.delivery_allowed and as_of >= self.force_exit_date


@dataclass(frozen=True, slots=True)
class OpenInterestObservation:
    trade_date: date
    contract: str
    delivery_month: int
    open_interest: Decimal

    def __post_init__(self) -> None:
        if not self.contract:
            raise ValueError("contract must be non-empty")
        if self.delivery_month < 190001 or self.delivery_month > 999912:
            raise ValueError("delivery_month must use YYYYMM format")
        month = self.delivery_month % 100
        if month < 1 or month > 12:
            raise ValueError("delivery_month contains an invalid month")
        if self.open_interest < 0:
            raise ValueError("open_interest must be non-negative")


def select_main_contract(
    current_contract: str,
    decision_date: date,
    observations: tuple[OpenInterestObservation, ...],
    confirmation_days: int,
    threshold: Decimal,
) -> str:
    if confirmation_days <= 0:
        raise ValueError("confirmation_days must be positive")
    if threshold < 1:
        raise ValueError("switch threshold must be at least one")

    eligible = tuple(item for item in observations if item.trade_date <= decision_date)
    dates = sorted({item.trade_date for item in eligible})
    if len(dates) < confirmation_days:
        return current_contract
    confirmation_window = dates[-confirmation_days:]
    by_date = {
        trade_date: {
            item.contract: item for item in eligible if item.trade_date == trade_date
        }
        for trade_date in confirmation_window
    }
    current_rows = [rows.get(current_contract) for rows in by_date.values()]
    if any(row is None for row in current_rows):
        return current_contract

    typed_current = [row for row in current_rows if row is not None]
    current_delivery_month = typed_current[-1].delivery_month
    candidates = {
        item.contract
        for item in eligible
        if item.delivery_month > current_delivery_month
    }
    qualified: list[tuple[Decimal, int, str]] = []
    for candidate in candidates:
        candidate_rows = [by_date[day].get(candidate) for day in confirmation_window]
        if any(row is None for row in candidate_rows):
            continue
        typed_candidates = [row for row in candidate_rows if row is not None]
        if all(
            candidate_row.open_interest >= current_row.open_interest * threshold
            for candidate_row, current_row in zip(
                typed_candidates,
                typed_current,
                strict=True,
            )
        ):
            mean_open_interest = sum(
                (row.open_interest for row in typed_candidates),
                start=Decimal("0"),
            ) / Decimal(confirmation_days)
            qualified.append(
                (
                    mean_open_interest,
                    -typed_candidates[-1].delivery_month,
                    candidate,
                )
            )

    if not qualified:
        return current_contract
    return max(qualified)[2]
