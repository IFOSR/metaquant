from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from quant_platform.markets.clocks import (
    AsiaShanghaiClock,
    CnAShareClock,
    CommodityFuturesClock,
    FuturesSessionTemplate,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_cn_a_clock_uses_post_close_signal_and_explicit_next_trade_date() -> None:
    clock = CnAShareClock()

    events = clock.events(
        trade_date=date(2026, 2, 13),
        next_trade_date=date(2026, 2, 24),
    )

    assert events.decision_at == datetime(2026, 2, 13, 15, 30, tzinfo=SHANGHAI)
    assert events.trade_at == datetime(2026, 2, 24, 9, 35, tzinfo=SHANGHAI)


@pytest.mark.parametrize(
    ("symbol", "night_end", "timestamp", "expected_trade_date"),
    [
        ("AU", time(2, 30), datetime(2026, 8, 10, 21, 1), date(2026, 8, 11)),
        ("AU", time(2, 30), datetime(2026, 8, 11, 2, 29), date(2026, 8, 11)),
        ("CU", time(1, 0), datetime(2026, 8, 10, 23, 59), date(2026, 8, 11)),
        ("RB", time(23, 0), datetime(2026, 8, 10, 22, 59), date(2026, 8, 11)),
        ("RB", time(23, 0), datetime(2026, 8, 11, 10, 0), date(2026, 8, 11)),
    ],
)
def test_futures_clock_assigns_night_and_day_sessions_to_exchange_trade_date(
    symbol: str,
    night_end: time,
    timestamp: datetime,
    expected_trade_date: date,
) -> None:
    clock = CommodityFuturesClock(
        FuturesSessionTemplate(
            product=symbol,
            night_start=time(21),
            night_end=night_end,
            settlement_at=time(15, 15),
        ),
        night_trade_dates={date(2026, 8, 10): date(2026, 8, 11)},
        trading_dates=frozenset({date(2026, 8, 11)}),
    )

    assert clock.trade_date(AsiaShanghaiClock.localize(timestamp)) == (
        expected_trade_date
    )


def test_futures_clock_does_not_invent_a_holiday_eve_night_session() -> None:
    clock = CommodityFuturesClock(
        FuturesSessionTemplate(
            product="AU",
            night_start=time(21),
            night_end=time(2, 30),
            settlement_at=time(15, 15),
        ),
        night_trade_dates={},
        trading_dates=frozenset({date(2026, 10, 9)}),
    )

    with pytest.raises(ValueError, match="no declared night session"):
        clock.trade_date(
            datetime(2026, 9, 30, 21, 1, tzinfo=SHANGHAI),
        )


def test_futures_settlement_clock_is_distinct_from_session_close() -> None:
    clock = CommodityFuturesClock(
        FuturesSessionTemplate(
            product="M",
            night_start=time(21),
            night_end=time(23),
            settlement_at=time(15, 15),
        ),
        night_trade_dates={date(2026, 8, 10): date(2026, 8, 11)},
        trading_dates=frozenset({date(2026, 8, 11)}),
    )

    assert clock.settlement_time(date(2026, 8, 11)) == datetime(
        2026, 8, 11, 15, 15, tzinfo=SHANGHAI
    )
