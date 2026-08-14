"""Five-clock event model for the backtest engine (G9).

The backtest ledger separates five clocks so a signal can never fill at the
same price it observed, and settlement cannot be confused with close
valuation. The clocks are:

- ``DATA_AVAILABLE``: point-in-time data becomes visible.
- ``SIGNAL``: the factor/strategy produces target positions.
- ``ORDER``: orders are generated after tradability checks.
- ``FILL``: the execution model produces fills on the next session.
- ``SETTLEMENT``: commodity-futures daily settlement (margin, marked-to-market).
- ``VALUATION``: end-of-period valuation, attribution, and audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum

from quant_platform.markets.clocks import SHANGHAI


class ClockKind(StrEnum):
    DATA_AVAILABLE = "DATA_AVAILABLE"
    SIGNAL = "SIGNAL"
    ORDER = "ORDER"
    FILL = "FILL"
    SETTLEMENT = "SETTLEMENT"
    VALUATION = "VALUATION"


_CLOCK_ORDER: tuple[ClockKind, ...] = (
    ClockKind.DATA_AVAILABLE,
    ClockKind.SIGNAL,
    ClockKind.ORDER,
    ClockKind.FILL,
    ClockKind.SETTLEMENT,
    ClockKind.VALUATION,
)


def clock_order(kind: ClockKind) -> int:
    return _CLOCK_ORDER.index(kind)


@dataclass(frozen=True, slots=True)
class ClockEvent:
    """One timestamped event on the backtest clock."""

    kind: ClockKind
    event_time: datetime
    trade_date: date

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ClockKind):
            object.__setattr__(self, "kind", ClockKind(self.kind))
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")


def _combine(day: date, hour: int, minute: int) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=SHANGHAI)


def a_share_daily_events(trading_dates: tuple[date, ...]) -> tuple[ClockEvent, ...]:
    """Generate the ordered A-share daily five-clock event sequence.

    Signal and order happen after T close; fills happen on the T+1 open, so a
    signal can never fill at the close price it observed. Valuation happens at
    T close on the positions held into the close.
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

    events: list[ClockEvent] = []
    for index, trade_date in enumerate(trading_dates):
        data_at = _combine(trade_date, 15, 0)
        signal_at = _combine(trade_date, 15, 30)
        events.append(ClockEvent(ClockKind.DATA_AVAILABLE, data_at, trade_date))
        events.append(ClockEvent(ClockKind.SIGNAL, signal_at, trade_date))
        events.append(ClockEvent(ClockKind.ORDER, signal_at, trade_date))
        events.append(ClockEvent(ClockKind.VALUATION, data_at, trade_date))
        if index + 1 < len(trading_dates):
            fill_at = _combine(trading_dates[index + 1], 9, 35)
            events.append(ClockEvent(ClockKind.FILL, fill_at, trade_date))

    return tuple(
        sorted(events, key=lambda event: (event.event_time, clock_order(event.kind)))
    )


def commodity_futures_daily_events(
    trading_dates: tuple[date, ...],
) -> tuple[ClockEvent, ...]:
    """Generate commodity-futures daily events with an added settlement clock.

    The settlement clock is distinct from close valuation: it drives margin
    requirement, marked-to-market P&L, and available cash, and must not be
    substituted by the close valuation clock.
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

    events: list[ClockEvent] = []
    for index, trade_date in enumerate(trading_dates):
        data_at = _combine(trade_date, 15, 0)
        signal_at = _combine(trade_date, 15, 30)
        settlement_at = _combine(trade_date, 15, 30)
        events.append(ClockEvent(ClockKind.DATA_AVAILABLE, data_at, trade_date))
        events.append(ClockEvent(ClockKind.SIGNAL, signal_at, trade_date))
        events.append(ClockEvent(ClockKind.ORDER, signal_at, trade_date))
        events.append(ClockEvent(ClockKind.SETTLEMENT, settlement_at, trade_date))
        events.append(ClockEvent(ClockKind.VALUATION, data_at, trade_date))
        if index + 1 < len(trading_dates):
            fill_at = _combine(trading_dates[index + 1], 9, 35)
            events.append(ClockEvent(ClockKind.FILL, fill_at, trade_date))

    return tuple(
        sorted(events, key=lambda event: (event.event_time, clock_order(event.kind)))
    )
