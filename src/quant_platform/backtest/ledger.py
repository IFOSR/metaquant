"""Backtest ledger contracts (G9-002).

Deterministic money, position, and fill accounting in decimal arithmetic. The
ledger records each fill and a per-period NAV history, and rejects any order or
fill that would violate non-negative cash or position invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from quant_platform.markets.cn_a import OrderSide

_ZERO = Decimal("0")


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    instrument_id: str
    side: OrderSide
    quantity: int
    trade_date: date

    def __post_init__(self) -> None:
        _require_identifier(self.order_id, "order_id")
        _require_identifier(self.instrument_id, "instrument_id")
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide(self.side))
        if self.quantity <= 0:
            raise ValueError("order quantity must be positive")


@dataclass(frozen=True, slots=True)
class Fill:
    fill_id: str
    order_id: str
    instrument_id: str
    side: OrderSide
    quantity: int
    price: Decimal
    cost: Decimal
    fill_time: datetime
    trade_date: date

    def __post_init__(self) -> None:
        _require_identifier(self.fill_id, "fill_id")
        _require_identifier(self.order_id, "order_id")
        _require_identifier(self.instrument_id, "instrument_id")
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide(self.side))
        if self.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if self.price <= _ZERO:
            raise ValueError("fill price must be positive")
        if self.cost < _ZERO:
            raise ValueError("fill cost must be non-negative")
        _require_aware(self.fill_time, "fill_time")


@dataclass(frozen=True, slots=True)
class Position:
    instrument_id: str
    quantity: int
    average_cost: Decimal

    def __post_init__(self) -> None:
        _require_identifier(self.instrument_id, "instrument_id")
        if self.quantity <= 0:
            raise ValueError("position quantity must be positive")
        if self.average_cost < _ZERO:
            raise ValueError("position average_cost must be non-negative")

    def payload(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "quantity": self.quantity,
            "average_cost": str(self.average_cost),
        }


@dataclass(frozen=True, slots=True)
class Ledger:
    cash: Decimal
    positions: tuple[Position, ...]
    fills: tuple[Fill, ...]
    nav_history: tuple[tuple[date, Decimal], ...] = ()

    def __post_init__(self) -> None:
        if self.cash < _ZERO:
            raise ValueError("cash must be non-negative")
        instruments = [item.instrument_id for item in self.positions]
        if len(set(instruments)) != len(instruments):
            raise ValueError("ledger positions must be unique per instrument")

    def position(self, instrument_id: str) -> Position | None:
        for item in self.positions:
            if item.instrument_id == instrument_id:
                return item
        return None

    def apply_fill(self, fill: Fill) -> Ledger:
        """Apply a fill, updating cash and positions deterministically."""
        current = self.position(fill.instrument_id)
        if fill.side is OrderSide.BUY:
            outlay = fill.price * fill.quantity + fill.cost
            new_cash = self.cash - outlay
            if new_cash < _ZERO:
                raise ValueError("INSUFFICIENT_CASH")
            new_quantity = (current.quantity if current else 0) + fill.quantity
            new_cost = (
                (current.average_cost * current.quantity + fill.price * fill.quantity)
                / new_quantity
                if current
                else fill.price
            )
        else:
            if current is None or current.quantity < fill.quantity:
                raise ValueError("INSUFFICIENT_POSITION")
            proceeds = fill.price * fill.quantity - fill.cost
            new_cash = self.cash + proceeds
            new_quantity = current.quantity - fill.quantity
            new_cost = current.average_cost

        positions = [
            item for item in self.positions if item.instrument_id != fill.instrument_id
        ]
        if new_quantity > 0:
            positions.append(
                Position(
                    instrument_id=fill.instrument_id,
                    quantity=new_quantity,
                    average_cost=new_cost,
                )
            )
        return Ledger(
            cash=new_cash,
            positions=tuple(sorted(positions, key=lambda item: item.instrument_id)),
            fills=self.fills + (fill,),
            nav_history=self.nav_history,
        )

    def nav(self, prices: dict[str, Decimal]) -> Decimal:
        """Mark positions to the given prices and return total NAV."""
        total = self.cash
        for position in self.positions:
            price = prices.get(position.instrument_id)
            if price is None:
                raise ValueError(f"missing price for {position.instrument_id}")
            if price <= _ZERO:
                raise ValueError(f"price must be positive for {position.instrument_id}")
            total += price * position.quantity
        return total

    def mark_to_market(self, prices: dict[str, Decimal], trade_date: date) -> Ledger:
        """Append a NAV observation for the given trade date."""
        value = self.nav(prices)
        return Ledger(
            cash=self.cash,
            positions=self.positions,
            fills=self.fills,
            nav_history=self.nav_history + ((trade_date, value),),
        )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "backtest-ledger/v1",
            "cash": str(self.cash),
            "positions": [item.payload() for item in self.positions],
            "fills": [
                {
                    "fill_id": item.fill_id,
                    "order_id": item.order_id,
                    "instrument_id": item.instrument_id,
                    "side": item.side.value,
                    "quantity": item.quantity,
                    "price": str(item.price),
                    "cost": str(item.cost),
                    "fill_time": item.fill_time.isoformat(),
                    "trade_date": item.trade_date.isoformat(),
                }
                for item in self.fills
            ],
            "nav_history": [
                {"trade_date": day.isoformat(), "nav": str(value)}
                for day, value in self.nav_history
            ],
        }
