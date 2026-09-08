"""端到端回归：双周期 MACD + ADX + 移动止损信号 spec 能产生交易。

这是本次修复 48 笔案例的等价信号化写法：验证信号模型能表达
「日线趋势过滤 + 执行周期 MACD 金叉 + ADX 门槛 + ATR 移动止损」，
并在代表性行情上产生交易。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from quant_platform.data_gateway.resolver import Bar
from quant_platform.signal.runner import run_signal_backtest

SHANGHAI = ZoneInfo("Asia/Shanghai")

_SIGNAL = """
INDICATORS = [
    {"key": "macd", "type": "macd", "fast": 3, "slow": 8, "signal": 5},
    {"key": "atr", "type": "atr", "period": 5},
    {"key": "adx", "type": "adx", "period": 5},
]

def compute_signal(ctx):
    if not ctx.ready:
        return Signal(target_qty=0)
    trend_up = ctx.trend.macd.dif > 0
    strong = ctx.trend.adx.adx >= 10
    if ctx.position == 0:
        if trend_up and strong:
            return Signal(
                target_qty=1,
                stop_price=ctx.bar.close - 2 * ctx.exec.atr.value,
            )
        return Signal(target_qty=0)
    # 持仓：趋势转弱即平，否则移动止损
    if not trend_up:
        return Signal(target_qty=0)
    stop = max(ctx.stop_price, ctx.bar.close - 2 * ctx.exec.atr.value)
    return Signal(target_qty=1, stop_price=stop)
"""


def _daily_bars(days: int = 40) -> tuple[Bar, ...]:
    base = datetime(2026, 1, 5, 15, 0, tzinfo=SHANGHAI)
    bars: list[Bar] = []
    close = 100.0
    for i in range(days):
        close += 1.0
        bars.append(
            Bar(
                timestamp=base + timedelta(days=i),
                open=close - 0.5,
                high=close + 1.0,
                low=close - 0.5,
                close=close,
                volume=1000.0,
            )
        )
    return tuple(bars)


def _minute_bars(days: int = 20, bars_per_day: int = 8) -> tuple[Bar, ...]:
    base = datetime(2026, 1, 5, 9, 5, tzinfo=SHANGHAI)
    bars: list[Bar] = []
    close = 100.0
    for day in range(days):
        for index in range(bars_per_day):
            close += 0.2
            ts = base + timedelta(days=day, minutes=5 * index)
            bars.append(
                Bar(
                    timestamp=ts,
                    open=close - 0.2,
                    high=close + 0.3,
                    low=close - 0.2,
                    close=close,
                    volume=100.0,
                )
            )
    return tuple(bars)


def test_dual_timeframe_signal_produces_trades() -> None:
    result = run_signal_backtest(
        code=_SIGNAL,
        market="CN_COMMODITY_FUTURES",
        instrument_ids=("SA8888.CZC",),
        bars_by_instrument={"SA8888.CZC": _minute_bars()},
        frequency="15m",
        trend_bars_by_instrument={"SA8888.CZC": _daily_bars()},
        trend_frequency="1d",
        initial_cash=Decimal("1000000"),
    )
    assert result.trades
    assert result.metrics.trade_count > 0
