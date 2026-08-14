"""Commodity-futures backtest engine (G9-004).

Futures execution differs from equities in three ways modeled here: positions
are directional (long/short), every position requires margin, and each day is
marked to the settlement price. The engine is deterministic and uses decimal
arithmetic throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from quant_platform.experiments import canonical_hash
from quant_platform.markets.clocks import SHANGHAI

_ZERO = Decimal("0")


class FuturesDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True, slots=True)
class FuturesPosition:
    instrument_id: str
    direction: FuturesDirection
    quantity: int
    average_price: Decimal

    def __post_init__(self) -> None:
        if not self.instrument_id or self.instrument_id.strip() != self.instrument_id:
            raise ValueError("instrument_id must be a non-empty normalized identifier")
        if not isinstance(self.direction, FuturesDirection):
            object.__setattr__(self, "direction", FuturesDirection(self.direction))
        if self.quantity <= 0:
            raise ValueError("position quantity must be positive")
        if self.average_price <= _ZERO:
            raise ValueError("average_price must be positive")

    def notional(self, multiplier: Decimal) -> Decimal:
        return self.average_price * self.quantity * multiplier

    def payload(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "direction": self.direction.value,
            "quantity": self.quantity,
            "average_price": str(self.average_price),
        }


@dataclass(frozen=True, slots=True)
class FuturesFill:
    fill_id: str
    instrument_id: str
    direction: FuturesDirection
    quantity: int
    price: Decimal
    fee: Decimal
    fill_time: datetime
    trade_date: date

    def __post_init__(self) -> None:
        if not self.fill_id or self.fill_id.strip() != self.fill_id:
            raise ValueError("fill_id must be a non-empty normalized identifier")
        if not isinstance(self.direction, FuturesDirection):
            object.__setattr__(self, "direction", FuturesDirection(self.direction))
        if self.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if self.price <= _ZERO:
            raise ValueError("fill price must be positive")
        if self.fee < _ZERO:
            raise ValueError("fee must be non-negative")


@dataclass(frozen=True, slots=True)
class FuturesLedger:
    cash: Decimal
    positions: tuple[FuturesPosition, ...]
    fills: tuple[FuturesFill, ...]
    nav_history: tuple[tuple[date, Decimal], ...] = ()

    def __post_init__(self) -> None:
        if self.cash < _ZERO:
            raise ValueError("cash must be non-negative")
        keys = [(item.instrument_id, item.direction) for item in self.positions]
        if len(set(keys)) != len(keys):
            raise ValueError("positions must be unique per instrument and direction")

    def margin_requirement(self, multiplier: Decimal, margin_rate: Decimal) -> Decimal:
        total = _ZERO
        for position in self.positions:
            total += position.notional(multiplier) * margin_rate
        return total

    def nav(
        self,
        settlement_prices: dict[str, Decimal],
        multiplier: Decimal,
    ) -> Decimal:
        """NAV at settlement prices: cash plus unrealized P&L on each position."""
        total = self.cash
        for position in self.positions:
            price = settlement_prices[position.instrument_id]
            sign = (
                Decimal("1")
                if position.direction is FuturesDirection.LONG
                else Decimal("-1")
            )
            total += (
                (price - position.average_price) * position.quantity * sign * multiplier
            )
        return total

    def settle(
        self,
        settlement_prices: dict[str, Decimal],
        trade_date: date,
        multiplier: Decimal,
    ) -> FuturesLedger:
        """Record a NAV snapshot at the settlement price.

        The snapshot includes unrealized P&L; realized P&L is booked when a
        position is closed, so a settlement is never double-counted.
        """
        value = self.nav(settlement_prices, multiplier)
        return FuturesLedger(
            cash=self.cash,
            positions=self.positions,
            fills=self.fills,
            nav_history=self.nav_history + ((trade_date, value),),
        )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "futures-ledger/v1",
            "cash": str(self.cash),
            "positions": [item.payload() for item in self.positions],
            "fills": [
                {
                    "fill_id": item.fill_id,
                    "instrument_id": item.instrument_id,
                    "direction": item.direction.value,
                    "quantity": item.quantity,
                    "price": str(item.price),
                    "fee": str(item.fee),
                    "fill_time": item.fill_time.isoformat(),
                    "trade_date": item.trade_date.isoformat(),
                }
                for item in self.fills
            ],
            "nav_history": [
                {"trade_date": day.isoformat(), "cash": str(value)}
                for day, value in self.nav_history
            ],
        }


@dataclass(frozen=True, slots=True)
class FuturesBacktestResult:
    ledger: FuturesLedger
    margin_used: Decimal
    blocked: tuple[tuple[str, str], ...]

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "futures-backtest-result/v1",
            "ledger": self.ledger.payload(),
            "margin_used": str(self.margin_used),
            "blocked": [
                {"instrument_id": item[0], "reason": item[1]} for item in self.blocked
            ],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def _open_time(day: date) -> datetime:
    return datetime.combine(day, time(9, 0), tzinfo=SHANGHAI)


def run_futures_backtest(
    *,
    trading_dates: tuple[date, ...],
    settlement_prices: dict[date, dict[str, Decimal]],
    open_prices: dict[date, dict[str, Decimal]],
    target_positions: dict[date, dict[str, tuple[FuturesDirection, int]]],
    margin_rate: Decimal,
    fee_rate: Decimal,
    contract_multiplier: Decimal,
    initial_cash: Decimal,
) -> FuturesBacktestResult:
    """Run a deterministic commodity-futures daily backtest.

    Target positions are directional (LONG/SHORT) quantities. Orders fill at
    the next session open after a margin check; each day the ledger is marked
    to the settlement price and P&L is realized into cash.
    """
    if not trading_dates:
        raise ValueError("trading_dates must not be empty")
    if len(set(trading_dates)) != len(trading_dates):
        raise ValueError("trading_dates must be unique")
    if any(
        second <= first
        for first, second in zip(trading_dates, trading_dates[1:], strict=False)
    ):
        raise ValueError("trading_dates must be strictly increasing")
    if not _ZERO < margin_rate <= Decimal("1"):
        raise ValueError("margin_rate must be within (0, 1]")
    if fee_rate < _ZERO:
        raise ValueError("fee_rate must be non-negative")
    if contract_multiplier <= _ZERO:
        raise ValueError("contract_multiplier must be positive")
    if initial_cash <= _ZERO:
        raise ValueError("initial_cash must be positive")

    ledger = FuturesLedger(cash=initial_cash, positions=(), fills=())
    blocked: list[tuple[str, str]] = []

    for index, trade_date in enumerate(trading_dates):
        settle = settlement_prices.get(trade_date, {})

        # Daily settlement: realize P&L at the settlement price.
        if ledger.positions:
            ledger = ledger.settle(settle, trade_date, contract_multiplier)

        # Signal: reconcile target positions for the next session.
        if index + 1 >= len(trading_dates):
            continue
        open_next = open_prices.get(trading_dates[index + 1], {})
        targets = target_positions.get(trade_date, {})

        current_map = {item.instrument_id: item for item in ledger.positions}
        all_instruments = sorted(set(current_map) | set(targets))

        for instrument_id in all_instruments:
            target = targets.get(instrument_id)
            position = current_map.get(instrument_id)

            if target is None:
                if position is None:
                    continue
                direction = position.direction
                quantity = 0
            else:
                direction, quantity = target
                if quantity < 0:
                    raise ValueError("target quantity must be non-negative")

            current_qty = (
                position.quantity
                if position is not None and position.direction is direction
                else 0
            )
            if quantity == current_qty:
                continue
            open_price = open_next.get(instrument_id)
            if open_price is None or open_price <= _ZERO:
                blocked.append((instrument_id, "no_open_price"))
                continue

            delta = quantity - current_qty
            if delta > 0:
                # Opening/increasing a position requires margin.
                margin = open_price * delta * contract_multiplier * margin_rate
                fee = open_price * delta * contract_multiplier * fee_rate
                if ledger.cash < margin + fee:
                    blocked.append((instrument_id, "insufficient_margin"))
                    continue
                fill = FuturesFill(
                    fill_id=f"fill_{trade_date.isoformat()}_{instrument_id}_{direction.value}",
                    instrument_id=instrument_id,
                    direction=direction,
                    quantity=delta,
                    price=open_price,
                    fee=fee,
                    fill_time=_open_time(trading_dates[index + 1]),
                    trade_date=trading_dates[index + 1],
                )
                ledger = _apply_open(ledger, fill, fee)
            else:
                fill = FuturesFill(
                    fill_id=f"fill_{trade_date.isoformat()}_{instrument_id}_{direction.value}",
                    instrument_id=instrument_id,
                    direction=direction,
                    quantity=-delta,
                    price=open_price,
                    fee=open_price * (-delta) * contract_multiplier * fee_rate,
                    fill_time=_open_time(trading_dates[index + 1]),
                    trade_date=trading_dates[index + 1],
                )
                ledger = _apply_close(ledger, fill, contract_multiplier)

    margin_used = ledger.margin_requirement(contract_multiplier, margin_rate)
    return FuturesBacktestResult(
        ledger=ledger, margin_used=margin_used, blocked=tuple(blocked)
    )


def _apply_open(
    ledger: FuturesLedger, fill: FuturesFill, cash_out: Decimal
) -> FuturesLedger:
    position = next(
        (
            item
            for item in ledger.positions
            if item.instrument_id == fill.instrument_id
            and item.direction is fill.direction
        ),
        None,
    )
    if position is None:
        new_position = FuturesPosition(
            instrument_id=fill.instrument_id,
            direction=fill.direction,
            quantity=fill.quantity,
            average_price=fill.price,
        )
    else:
        new_quantity = position.quantity + fill.quantity
        new_price = (
            position.average_price * position.quantity + fill.price * fill.quantity
        ) / new_quantity
        new_position = FuturesPosition(
            instrument_id=fill.instrument_id,
            direction=fill.direction,
            quantity=new_quantity,
            average_price=new_price,
        )
    positions = [
        item
        for item in ledger.positions
        if not (
            item.instrument_id == fill.instrument_id
            and item.direction is fill.direction
        )
    ]
    positions.append(new_position)
    return FuturesLedger(
        cash=ledger.cash - cash_out,
        positions=tuple(
            sorted(
                positions, key=lambda item: (item.instrument_id, item.direction.value)
            )
        ),
        fills=ledger.fills + (fill,),
        nav_history=ledger.nav_history,
    )


def _apply_close(
    ledger: FuturesLedger, fill: FuturesFill, multiplier: Decimal
) -> FuturesLedger:
    position = next(
        (
            item
            for item in ledger.positions
            if item.instrument_id == fill.instrument_id
            and item.direction is fill.direction
        ),
        None,
    )
    if position is None or position.quantity < fill.quantity:
        raise ValueError("INSUFFICIENT_POSITION")
    sign = (
        Decimal("1") if position.direction is FuturesDirection.LONG else Decimal("-1")
    )
    pnl = (fill.price - position.average_price) * fill.quantity * sign * multiplier
    fee = fill.fee
    remaining = position.quantity - fill.quantity
    positions = [
        item
        for item in ledger.positions
        if not (
            item.instrument_id == fill.instrument_id
            and item.direction is fill.direction
        )
    ]
    if remaining > 0:
        positions.append(
            FuturesPosition(
                instrument_id=position.instrument_id,
                direction=position.direction,
                quantity=remaining,
                average_price=position.average_price,
            )
        )
    return FuturesLedger(
        cash=ledger.cash + pnl - fee,
        positions=tuple(
            sorted(
                positions, key=lambda item: (item.instrument_id, item.direction.value)
            )
        ),
        fills=ledger.fills + (fill,),
        nav_history=ledger.nav_history,
    )


def floor_lots(notional: Decimal, price: Decimal, multiplier: Decimal) -> int:
    """Convert a notional target into a whole-lot contract count."""
    if price <= _ZERO or multiplier <= _ZERO:
        return 0
    return int((notional / price / multiplier).to_integral_value(rounding=ROUND_DOWN))
