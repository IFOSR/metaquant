"""Tests for signal backtest shared helpers + code-test gate.

策略执行本身已信号化（见 ``tests/signal/``）；本文件只覆盖仍在本模块的
共享件：bar 聚合、T+1 审计、code test 门禁。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from quant_platform.backtest.service import BacktestTrade
from quant_platform.data_gateway.resolver import Bar
from quant_platform.strategy_generation.backtest import (
    _audit_t_plus_one,
    aggregate_bars,
    code_test_strategy,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")

_ALWAYS_BUY = (
    "INDICATORS = []\ndef compute_signal(ctx):\n    return Signal(target_qty=1)\n"
)


def _daily_bars(days: int = 30) -> tuple[Bar, ...]:
    base = datetime(2026, 1, 5, 15, 0, tzinfo=SHANGHAI)
    price = 10.0
    bars: list[Bar] = []
    for i in range(days):
        price += 0.1
        bars.append(
            Bar(
                timestamp=base + timedelta(days=i),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1000.0,
            )
        )
    return tuple(bars)


def _minute_bars(days: int = 5, bars_per_day: int = 6) -> tuple[Bar, ...]:
    """每个交易日 6 根 5m bar（09:05 ~ 09:30），价格缓涨。"""
    base = datetime(2026, 1, 5, 9, 5, tzinfo=SHANGHAI)
    bars: list[Bar] = []
    price = 10.0
    for day in range(days):
        for index in range(bars_per_day):
            price += 0.05
            ts = base + timedelta(days=day, minutes=5 * index)
            bars.append(
                Bar(
                    timestamp=ts,
                    open=price,
                    high=price + 0.02,
                    low=price - 0.02,
                    close=price,
                    volume=100.0,
                )
            )
    return tuple(bars)


# ── T+1 审计 ──────────────────────────────────────────────────────────────


def test_t_plus_one_audit_flags_same_day_round_trip() -> None:
    day = datetime(2026, 1, 5, 9, 35, tzinfo=SHANGHAI)
    trades = (
        BacktestTrade(
            time=day.isoformat(),
            instrument_id="600000.SSE",
            side="BUY",
            quantity=100,
            price=10.0,
        ),
        BacktestTrade(
            time=day.isoformat(),
            instrument_id="600000.SSE",
            side="SELL",
            quantity=100,
            price=10.1,
        ),
    )
    violations = _audit_t_plus_one(trades=trades, id_map={})
    assert violations
    assert "t_plus_one_violation" in violations[0]


def test_t_plus_one_audit_allows_next_day_exit() -> None:
    day_one = datetime(2026, 1, 5, 15, 0, tzinfo=SHANGHAI)
    day_two = datetime(2026, 1, 6, 15, 0, tzinfo=SHANGHAI)
    trades = (
        BacktestTrade(
            time=day_one.isoformat(),
            instrument_id="600000.SSE",
            side="BUY",
            quantity=100,
            price=10.0,
        ),
        BacktestTrade(
            time=day_two.isoformat(),
            instrument_id="600000.SSE",
            side="SELL",
            quantity=100,
            price=10.1,
        ),
    )
    assert _audit_t_plus_one(trades=trades, id_map={}) == ()


# ── bar 聚合 ──────────────────────────────────────────────────────────────


def test_aggregate_bars_5m_to_15m() -> None:
    bars = _minute_bars(days=1, bars_per_day=6)
    aggregated = aggregate_bars(bars, "15m")
    assert len(aggregated) == 2  # 6 根 5m → 2 根 15m
    first = aggregated[0]
    assert first.open == bars[0].open
    assert first.close == bars[2].close
    assert first.high == max(bar.high for bar in bars[:3])
    assert first.low == min(bar.low for bar in bars[:3])
    assert first.volume == sum(bar.volume for bar in bars[:3])


def test_aggregate_bars_daily_to_weekly() -> None:
    bars = _daily_bars(14)  # 两周日线
    aggregated = aggregate_bars(bars, "1w")
    assert 1 < len(aggregated) < 14
    assert aggregated[0].open == bars[0].open
    assert all(
        aggregated[i].timestamp <= aggregated[i + 1].timestamp
        for i in range(len(aggregated) - 1)
    )


def test_aggregate_bars_passthrough_base() -> None:
    bars = _daily_bars(5)
    assert aggregate_bars(bars, "1d") == bars
    minute = _minute_bars(days=1)
    assert aggregate_bars(minute, "5m") == minute


# ── code test 门禁 ────────────────────────────────────────────────────────


def test_code_test_strategy_passes_valid_strategy() -> None:
    """代码正确性测试：合法信号 spec 应在基础行情上跑通并产生信号。"""
    result = code_test_strategy(
        code=_ALWAYS_BUY,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": _daily_bars(30)},
        frequency="1d",
    )
    assert result.passed is True
    assert result.exit_code == 0
    assert result.duration_ms >= 0


def test_code_test_strategy_fails_policy_violation() -> None:
    """代码正确性测试：违反隔离策略（import）的代码必须被拦截。"""
    result = code_test_strategy(
        code="import os\n" + _ALWAYS_BUY,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": _daily_bars(30)},
        frequency="1d",
    )
    assert result.passed is False
    assert result.exit_code != 0
    assert "import" in result.stderr


def test_code_test_strategy_fails_when_no_trades() -> None:
    """代码正确性测试：代表性数据上 0 成交 → 判定失败（抓「永远不成交」bug）。"""
    result = code_test_strategy(
        code=(
            "INDICATORS = []\n"
            "def compute_signal(ctx):\n"
            "    return Signal(target_qty=0)\n"
        ),
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": _daily_bars(30)},
        frequency="1d",
    )
    assert result.passed is False
    assert "no trades" in result.stderr
