"""Tests for the LiveFeed replay clock and PIT row mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from quant_platform.markets.nt.sessions import FUTURES_DAY_SESSIONS, FUTURES_NIGHT_SESSIONS
from quant_platform.paper.live_feed import VirtualMarketClock

SH = ZoneInfo("Asia/Shanghai")
SESSIONS = FUTURES_DAY_SESSIONS + FUTURES_NIGHT_SESSIONS
STEP = timedelta(minutes=5)


def clock_at(y, m, d, hh, mm):
    return VirtualMarketClock(
        start=datetime(y, m, d, hh, mm, tzinfo=SH), step=STEP, sessions=SESSIONS
    )


def test_clock_steps_within_session() -> None:
    clock = clock_at(2026, 8, 25, 9, 0)  # 周二 09:00 日盘开盘
    assert clock.advance() == datetime(2026, 8, 25, 9, 0, tzinfo=SH).astimezone(UTC)
    assert clock.advance() == datetime(2026, 8, 25, 9, 5, tzinfo=SH).astimezone(UTC)


def test_clock_skips_lunch_break() -> None:
    clock = clock_at(2026, 8, 25, 11, 25)
    clock.advance()  # 11:25
    # 11:30 不在任何时段内（11:30-13:30 休市）→ 跳到 13:30
    assert clock.advance() == datetime(2026, 8, 25, 13, 30, tzinfo=SH).astimezone(UTC)


def test_clock_skips_to_night_session() -> None:
    clock = clock_at(2026, 8, 25, 14, 55)
    clock.advance()  # 14:55
    # 15:00 收盘 → 跳到夜盘 21:00
    assert clock.advance() == datetime(2026, 8, 25, 21, 0, tzinfo=SH).astimezone(UTC)


def test_clock_skips_weekend() -> None:
    clock = clock_at(2026, 8, 21, 22, 55)  # 周五夜盘
    clock.advance()  # 22:55
    # 23:00 夜盘收盘 → 跳过周末 → 周一 09:00
    assert clock.advance() == datetime(2026, 8, 24, 9, 0, tzinfo=SH).astimezone(UTC)


def test_clock_aligns_start_outside_session() -> None:
    clock = clock_at(2026, 8, 25, 12, 0)  # 午间休市
    assert clock.advance() == datetime(2026, 8, 25, 13, 30, tzinfo=SH).astimezone(UTC)
