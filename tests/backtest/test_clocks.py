from __future__ import annotations

from datetime import date

import pytest

from quant_platform.backtest.clocks import (
    ClockKind,
    a_share_daily_events,
    commodity_futures_daily_events,
)


def dates(*days: int) -> tuple[date, ...]:
    return tuple(date(2026, 8, day) for day in days)


def test_a_share_events_are_time_ordered() -> None:
    events = a_share_daily_events(dates(3, 4, 5))

    times = [event.event_time for event in events]
    assert times == sorted(times)


def test_a_share_events_cover_all_clocks() -> None:
    events = a_share_daily_events(dates(3, 4, 5))

    kinds = {event.kind for event in events}
    assert ClockKind.DATA_AVAILABLE in kinds
    assert ClockKind.SIGNAL in kinds
    assert ClockKind.ORDER in kinds
    assert ClockKind.FILL in kinds
    assert ClockKind.VALUATION in kinds


def test_signal_precedes_fill() -> None:
    events = a_share_daily_events(dates(3, 4))

    signal = next(event for event in events if event.kind is ClockKind.SIGNAL)
    fill = next(event for event in events if event.kind is ClockKind.FILL)

    assert signal.event_time < fill.event_time


def test_last_date_has_no_fill() -> None:
    events = a_share_daily_events(dates(3, 4, 5))

    last = dates(3, 4, 5)[-1]
    fills_on_last = [
        event
        for event in events
        if event.kind is ClockKind.FILL and event.trade_date == last
    ]
    assert fills_on_last == []


def test_futures_events_include_settlement() -> None:
    events = commodity_futures_daily_events(dates(3, 4))

    assert ClockKind.SETTLEMENT in {event.kind for event in events}


def test_rejects_unordered_dates() -> None:
    with pytest.raises(ValueError):
        a_share_daily_events(dates(5, 4))


def test_rejects_duplicate_dates() -> None:
    with pytest.raises(ValueError):
        a_share_daily_events(dates(3, 3))


def test_rejects_empty_dates() -> None:
    with pytest.raises(ValueError):
        a_share_daily_events(())
