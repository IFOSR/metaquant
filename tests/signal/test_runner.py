"""共享 runner 测试：run_signal_backtest 端到端。"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from quant_platform.data_gateway.resolver import Bar
from quant_platform.signal.runner import run_signal_backtest

SHANGHAI = ZoneInfo("Asia/Shanghai")

_TARGET_ONE = "INDICATORS = []\ndef compute_signal(ctx):\n    return Signal(target_qty=1)\n"


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
