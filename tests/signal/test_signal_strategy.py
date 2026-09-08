"""SignalStrategy 共享执行器测试：目标仓位调仓 + 止损触发。"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from nautilus_trader.config import StrategyConfig

from quant_platform.data_gateway.resolver import Bar
from quant_platform.markets.nt import (
    build_equity_engine,
    day_bar_spec,
    equity_instrument,
    run_engine,
    to_nautilus_bars,
)
from quant_platform.signal.contract import load_signal_spec
from quant_platform.signal.strategy import SignalStrategy

SHANGHAI = ZoneInfo("Asia/Shanghai")

_TARGET_ONE = """
INDICATORS = []
def compute_signal(ctx):
    return Signal(target_qty=1)
"""

_ENTER_WITH_STOP = """
INDICATORS = []
def compute_signal(ctx):
    if ctx.position == 0:
        return Signal(target_qty=1, stop_price=ctx.bar.close - 5.0)
    return Signal(target_qty=1, stop_price=ctx.stop_price)
"""


def _bars(
    closes: tuple[float, ...], lows: dict[int, float] | None = None
) -> tuple[Bar, ...]:
    base = datetime(2026, 1, 5, 15, 0, tzinfo=SHANGHAI)
    bars: list[Bar] = []
    for i, close in enumerate(closes):
        low = lows.get(i, close - 0.1) if lows else close - 0.1
        bars.append(
            Bar(
                timestamp=base + timedelta(days=i),
                open=close,
                high=close + 0.1,
                low=low,
                close=close,
                volume=1000.0,
            )
        )
    return tuple(bars)


def _run(spec_code: str, bars: tuple[Bar, ...]):
    spec = load_signal_spec(spec_code)
    instrument = equity_instrument(symbol="600000", venue="SSE")
    engine = build_equity_engine(
        instrument=instrument, initial_cash=Decimal("1000000"), venue="SSE"
    )
    bar_type_str = f"{instrument.id}-1-DAY-LAST-EXTERNAL"
    strategy = SignalStrategy(
        StrategyConfig(strategy_id="sig-1"),
        instrument_id=str(instrument.id),
        bar_type_str=bar_type_str,
        spec=spec,
    )
    engine.add_strategy(strategy)
    nt_bars = to_nautilus_bars(
        bars, instrument_id=instrument.id, bar_spec=day_bar_spec(), price_precision=2
    )
    run_engine(engine, bars=list(nt_bars))
    return engine, strategy


def test_signal_strategy_target_position_orders() -> None:
    engine, _ = _run(_TARGET_ONE, _bars((10.0, 10.1, 10.2, 10.3)))
    fills = engine.trader.generate_order_fills_report()
    assert len(fills) >= 1


def test_signal_strategy_stop_loss_flattens() -> None:
    engine, strategy = _run(
        _ENTER_WITH_STOP,
        _bars((10.0, 10.1, 6.0), lows={2: 4.5}),
    )
    fills = engine.trader.generate_order_fills_report()
    sides = [str(row["side"]) for _, row in fills.iterrows()]
    assert "BUY" in sides and "SELL" in sides
    assert strategy.last_target == 0
