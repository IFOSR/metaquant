"""Backtest engine (G9).

Deterministic multi-clock backtesting with explicit data, signal, order, fill,
settlement, and valuation clocks, plus per-market execution semantics.
"""

from quant_platform.backtest.clocks import (
    ClockEvent,
    ClockKind,
    a_share_daily_events,
    commodity_futures_daily_events,
)
from quant_platform.backtest.engine import (
    BacktestResult,
    run_a_share_backtest,
)
from quant_platform.backtest.futures_engine import (
    FuturesBacktestResult,
    FuturesDirection,
    FuturesLedger,
    run_futures_backtest,
)
from quant_platform.backtest.ledger import (
    Fill,
    Ledger,
    Order,
    Position,
)

__all__ = [
    "BacktestResult",
    "ClockEvent",
    "ClockKind",
    "Fill",
    "FuturesBacktestResult",
    "FuturesDirection",
    "FuturesLedger",
    "Ledger",
    "Order",
    "Position",
    "a_share_daily_events",
    "commodity_futures_daily_events",
    "run_a_share_backtest",
    "run_futures_backtest",
]
