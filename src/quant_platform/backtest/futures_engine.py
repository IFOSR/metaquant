"""Commodity-futures backtest engine (G9-004, G16-003).

Futures execution differs from equities: positions are directional (long/short),
every position requires margin, and each day is marked to the settlement price
with daily settlement P&L realized into cash. The engine additionally models
close-today versus close-yesterday fee offsets, delivery-month forced exit,
price limits, and margin-based forced liquidation (FR-506).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum

from quant_platform.experiments import canonical_hash
from quant_platform.markets.clocks import SHANGHAI
from quant_platform.markets.futures import (
    CloseOffset,
    DeliveryPolicy,
    FeeSchedule,
)

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
    opened_on: date | None = None

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
            "opened_on": self.opened_on.isoformat() if self.opened_on else None,
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
    close_offset: CloseOffset | None = None

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
        # Cash may turn negative after a mark-to-market settlement books a loss
        # beyond the posted margin (the account owes the broker); forced
        # liquidation and margin calls handle the shortfall.
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
        """Daily mark-to-market settlement (FR-506).

        Realizes each position's P&L since its previous settlement into cash
        and resets the position's average price to the settlement price, so
        holding gains are booked daily rather than only at close.
        """
        cash = self.cash
        positions: list[FuturesPosition] = []
        for position in self.positions:
            price = settlement_prices[position.instrument_id]
            sign = (
                Decimal("1")
                if position.direction is FuturesDirection.LONG
                else Decimal("-1")
            )
            delta_price = price - position.average_price
            pnl = delta_price * position.quantity * sign * multiplier
            cash += pnl
            positions.append(replace(position, average_price=price))
        return FuturesLedger(
            cash=cash,
            positions=tuple(positions),
            fills=self.fills,
            nav_history=self.nav_history + ((trade_date, cash),),
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
                    "close_offset": (
                        item.close_offset.value if item.close_offset else None
                    ),
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
    forced_liquidations: tuple[tuple[str, str], ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "futures-backtest-result/v1",
            "ledger": self.ledger.payload(),
            "margin_used": str(self.margin_used),
            "blocked": [
                {"instrument_id": item[0], "reason": item[1]} for item in self.blocked
            ],
            "forced_liquidations": [
                {"instrument_id": item[0], "reason": item[1]}
                for item in self.forced_liquidations
            ],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def _open_time(day: date) -> datetime:
    return datetime.combine(day, time(9, 0), tzinfo=SHANGHAI)


def _close_fee(
    fee_rate: Decimal,
    fee_schedule: FeeSchedule | None,
    offset: CloseOffset,
    quantity: int,
    price: Decimal,
    multiplier: Decimal,
) -> Decimal:
    if fee_schedule is not None:
        return fee_schedule.calculate(offset, quantity, price, multiplier)
    return price * quantity * multiplier * fee_rate


def _sign(direction: FuturesDirection) -> Decimal:
    return Decimal("1") if direction is FuturesDirection.LONG else Decimal("-1")


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
    fee_schedule: FeeSchedule | None = None,
    delivery_policies: dict[str, DeliveryPolicy] | None = None,
    price_limits: dict[date, dict[str, tuple[Decimal, Decimal]]] | None = None,
    force_liquidate_on_margin: bool = True,
) -> FuturesBacktestResult:
    """Run a deterministic commodity-futures daily backtest (FR-506).

    Target positions are directional (LONG/SHORT) quantities. Orders fill at
    the next session open after a margin check; delivery-month policy forces
    exit; price limits block fills outside the day's band; each day the ledger
    is marked to market with settlement P&L realized into cash; and positions
    are force-liquidated at settlement when NAV drops below the margin
    requirement.
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
    forced: list[tuple[str, str]] = []

    for index, trade_date in enumerate(trading_dates):
        settle = settlement_prices.get(trade_date, {})

        # Daily mark-to-market settlement.
        if ledger.positions:
            ledger = ledger.settle(settle, trade_date, contract_multiplier)

        # Forced liquidation at settlement when NAV is below margin.
        if force_liquidate_on_margin and ledger.positions:
            required = ledger.margin_requirement(contract_multiplier, margin_rate)
            if ledger.nav(settle, contract_multiplier) < required:
                for position in ledger.positions:
                    forced.append((position.instrument_id, "forced_liquidation"))
                ledger = FuturesLedger(
                    cash=ledger.nav(settle, contract_multiplier),
                    positions=(),
                    fills=ledger.fills,
                    nav_history=ledger.nav_history,
                )

        # Signal: reconcile target positions for the next session.
        if index + 1 >= len(trading_dates):
            continue
        open_next = open_prices.get(trading_dates[index + 1], {})
        targets = target_positions.get(trade_date, {})

        current_map = {item.instrument_id: item for item in ledger.positions}
        all_instruments = sorted(set(current_map) | set(targets))

        for instrument_id in all_instruments:
            target = targets.get(instrument_id)
            current_position = current_map.get(instrument_id)

            # Delivery policy forces exit before the delivery month.
            policy = (delivery_policies or {}).get(instrument_id)
            if policy is not None and policy.must_exit(trade_date):
                target = None
            if (
                policy is not None
                and not policy.may_open(trade_date)
                and target is not None
                and target[1] > 0
            ):
                blocked.append((instrument_id, "delivery_restriction"))
                continue

            if target is None:
                if current_position is None:
                    continue
                direction = current_position.direction
                quantity = 0
            else:
                direction, quantity = target
                if quantity < 0:
                    raise ValueError("target quantity must be non-negative")

            current_qty = (
                current_position.quantity
                if current_position is not None
                and current_position.direction is direction
                else 0
            )
            if quantity == current_qty:
                continue
            open_price = open_next.get(instrument_id)
            if open_price is None or open_price <= _ZERO:
                blocked.append((instrument_id, "no_open_price"))
                continue

            # Price limit band on the fill date.
            limits = (
                (price_limits or {})
                .get(trading_dates[index + 1], {})
                .get(instrument_id)
            )
            if limits is not None and not limits[0] <= open_price <= limits[1]:
                blocked.append((instrument_id, "price_limit"))
                continue

            delta = quantity - current_qty
            fill_date = trading_dates[index + 1]
            if delta > 0:
                # Opening/increasing a position requires margin.
                margin = open_price * delta * contract_multiplier * margin_rate
                fee = _close_fee(
                    fee_rate,
                    fee_schedule,
                    CloseOffset.CLOSE_TODAY,
                    delta,
                    open_price,
                    contract_multiplier,
                )
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
                    fill_time=_open_time(fill_date),
                    trade_date=fill_date,
                )
                ledger = _apply_open(ledger, fill, fee, fill_date)
            else:
                ledger, close_ok = _apply_close(
                    ledger,
                    instrument_id,
                    direction,
                    -delta,
                    open_price,
                    contract_multiplier,
                    fill_date,
                    fee_rate,
                    fee_schedule,
                )
                if not close_ok:
                    blocked.append((instrument_id, "insufficient_position"))
                    continue

    margin_used = ledger.margin_requirement(contract_multiplier, margin_rate)
    return FuturesBacktestResult(
        ledger=ledger,
        margin_used=margin_used,
        blocked=tuple(blocked),
        forced_liquidations=tuple(forced),
    )


def _apply_open(
    ledger: FuturesLedger,
    fill: FuturesFill,
    cash_out: Decimal,
    opened_on: date,
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
            opened_on=opened_on,
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
            opened_on=position.opened_on,
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
    ledger: FuturesLedger,
    instrument_id: str,
    direction: FuturesDirection,
    quantity: int,
    price: Decimal,
    multiplier: Decimal,
    fill_date: date,
    fee_rate: Decimal,
    fee_schedule: FeeSchedule | None,
) -> tuple[FuturesLedger, bool]:
    """Close a quantity, preferring close-today lots (exchange rule).

    Close-today lots use the ``CLOSE_TODAY`` fee offset, close-yesterday lots
    use ``CLOSE_YESTERDAY``. Returns the ledger and whether the close succeeded.
    """
    position = next(
        (
            item
            for item in ledger.positions
            if item.instrument_id == instrument_id and item.direction is direction
        ),
        None,
    )
    if position is None or position.quantity < quantity:
        return ledger, False

    sign = _sign(direction)
    today_qty = quantity if position.opened_on == fill_date else 0
    yesterday_qty = quantity - today_qty
    pnl = (price - position.average_price) * quantity * sign * multiplier
    fee = _close_fee(
        fee_rate,
        fee_schedule,
        CloseOffset.CLOSE_TODAY,
        today_qty,
        price,
        multiplier,
    ) + _close_fee(
        fee_rate,
        fee_schedule,
        CloseOffset.CLOSE_YESTERDAY,
        yesterday_qty,
        price,
        multiplier,
    )
    fill = FuturesFill(
        fill_id=f"fill_{fill_date.isoformat()}_{instrument_id}_{direction.value}",
        instrument_id=instrument_id,
        direction=direction,
        quantity=quantity,
        price=price,
        fee=fee,
        fill_time=_open_time(fill_date),
        trade_date=fill_date,
        close_offset=(
            CloseOffset.CLOSE_TODAY if today_qty > 0 else CloseOffset.CLOSE_YESTERDAY
        ),
    )
    remaining = position.quantity - quantity
    positions = [
        item
        for item in ledger.positions
        if not (item.instrument_id == instrument_id and item.direction is direction)
    ]
    if remaining > 0:
        positions.append(replace(position, quantity=remaining))
    return (
        FuturesLedger(
            cash=ledger.cash + pnl - fee,
            positions=tuple(
                sorted(
                    positions,
                    key=lambda item: (item.instrument_id, item.direction.value),
                )
            ),
            fills=ledger.fills + (fill,),
            nav_history=ledger.nav_history,
        ),
        True,
    )
