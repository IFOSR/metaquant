"""共享 runner 测试：run_signal_backtest 端到端。"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from quant_platform.data_gateway.resolver import Bar
from quant_platform.signal.runner import run_signal_backtest
from quant_platform.strategy_generation.backtest import (
    StrategyLoadError,
    aggregate_bars,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")

_TARGET_ONE = (
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


def test_run_signal_backtest_produces_result() -> None:
    result = run_signal_backtest(
        code=_TARGET_ONE,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": _daily_bars()},
        frequency="1d",
        initial_cash=Decimal("1000000"),
    )
    assert result.trades
    assert result.metrics.trade_count >= 1
    assert len(result.backtest_hash) == 64
    assert result.positions
    payload = result.payload()
    assert payload["schema_version"] == "strategy-backtest/v1"
    assert payload["cost_basis"] == "net_of_fees"


def test_must_fire_when_entry_condition_satisfied() -> None:
    """must-fire 夹具：进场条件在喂入数据上无歧义成立 → 必须成交。

    用于机械地抓「自相矛盾的进场条件」这类永远不成交的 bug。
    """
    signal = (
        "INDICATORS = []\n"
        "def compute_signal(ctx):\n"
        "    if ctx.position == 0 and ctx.bar.close > 12.0:\n"
        "        return Signal(target_qty=1)\n"
        "    return Signal(target_qty=ctx.position)\n"
    )
    base = datetime(2026, 1, 5, 15, 0, tzinfo=SHANGHAI)
    bars = tuple(
        Bar(
            timestamp=base + timedelta(days=i),
            open=15.0,
            high=15.1,
            low=14.9,
            close=15.0,
            volume=1000.0,
        )
        for i in range(5)
    )
    result = run_signal_backtest(
        code=signal,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": bars},
        frequency="1d",
    )
    assert result.metrics.trade_count > 0


def _minute_bars(days: int = 5, bars_per_day: int = 6) -> tuple[Bar, ...]:
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


def test_run_signal_backtest_weekly_frequency() -> None:
    result = run_signal_backtest(
        code=_TARGET_ONE,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": aggregate_bars(_daily_bars(40), "1w")},
        frequency="1w",
        initial_cash=Decimal("1000000"),
    )
    assert result.trades
    assert result.equity_curve


def test_run_signal_backtest_multi_instrument_shared_account() -> None:
    """多标的组合回测：同一市场的两个标的共用一个账户，各自独立跑。"""
    result = run_signal_backtest(
        code=_TARGET_ONE,
        market="CN_A",
        instrument_ids=("600000.SH", "600519.SH"),
        bars_by_instrument={
            "600000.SH": _daily_bars(),
            "600519.SH": _daily_bars(),
        },
        frequency="1d",
        initial_cash=Decimal("1000000"),
    )
    assert result.trades
    traded = {trade.instrument_id for trade in result.trades}
    assert traded == {"600000.SSE", "600519.SSE"}


def test_run_signal_backtest_rejects_mixed_venues() -> None:
    with pytest.raises(StrategyLoadError, match="share one venue"):
        run_signal_backtest(
            code=_TARGET_ONE,
            market="CN_A",
            instrument_ids=("600000.SH", "000001.SZ"),
            bars_by_instrument={
                "600000.SH": _daily_bars(),
                "000001.SZ": _daily_bars(),
            },
            frequency="1d",
        )


def test_run_signal_backtest_requires_data() -> None:
    with pytest.raises(StrategyLoadError):
        run_signal_backtest(
            code=_TARGET_ONE,
            market="CN_A",
            instrument_ids=("600000.SH",),
            bars_by_instrument={},
            frequency="1d",
        )


def test_run_signal_backtest_rejects_market_instrument_mismatch() -> None:
    with pytest.raises(StrategyLoadError, match="market CN_A"):
        run_signal_backtest(
            code=_TARGET_ONE,
            market="CN_A",
            instrument_ids=("SA8888.CZC",),
            bars_by_instrument={"SA8888.CZC": _daily_bars()},
            frequency="1d",
        )


def test_run_signal_backtest_multi_timeframe() -> None:
    """日线趋势 + 5m 执行：趋势指标预热完成后（ctx.ready）才开仓。"""
    signal = (
        'INDICATORS = [{"key": "trend_sma", "type": "sma", "period": 3}]\n'
        "def compute_signal(ctx):\n"
        "    if not ctx.ready:\n"
        "        return Signal(target_qty=0)\n"
        "    if ctx.position == 0:\n"
        "        return Signal(target_qty=1)\n"
        "    return Signal(target_qty=ctx.position)\n"
    )
    result = run_signal_backtest(
        code=signal,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": _minute_bars(days=6)},
        frequency="5m",
        trend_bars_by_instrument={"600000.SH": _daily_bars(10)},
        trend_frequency="1d",
        initial_cash=Decimal("1000000"),
    )
    assert result.trades


def test_minute_equity_curve_preserves_intraday_timestamps() -> None:
    """分钟回测的曲线不能把同日成交压成一个日期点。"""
    result = run_signal_backtest(
        code=_TARGET_ONE,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": _minute_bars(days=5)},
        frequency="5m",
        initial_cash=Decimal("1000000"),
    )
    assert len(result.equity_curve) > len(
        {point[0][:10] for point in result.equity_curve}
    )
    assert any("T" in point[0] for point in result.equity_curve)
