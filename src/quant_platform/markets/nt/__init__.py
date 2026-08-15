"""NautilusTrader 适配层（G18）。

把 ``markets/`` 的规则建模（唯一事实源）映射到 NautilusTrader 的
Instrument / 数据 / 回测 / 执行。
"""

from quant_platform.markets.nt.backtest import build_equity_engine, run_engine
from quant_platform.markets.nt.data import (
    day_bar_spec,
    minute_bar_spec,
    to_nautilus_bar,
    to_nautilus_bars,
)
from quant_platform.markets.nt.execution_client import (
    NautilusOrderGateway,
    SubmitResult,
)
from quant_platform.markets.nt.fees import AShareFeeModel
from quant_platform.markets.nt.fills import PriceLimitFillModel
from quant_platform.markets.nt.instruments import (
    equity_instrument,
    futures_contract,
)
from quant_platform.markets.nt.sessions import (
    A_SHARE_SESSIONS,
    FUTURES_DAY_SESSIONS,
    FUTURES_NIGHT_SESSIONS,
    TradingSession,
    in_sessions,
    is_night_session,
)
from quant_platform.markets.nt.strategy_adapter import (
    RebalancePlan,
    StrategyAdapter,
)

__all__ = [
    "A_SHARE_SESSIONS",
    "AShareFeeModel",
    "FUTURES_DAY_SESSIONS",
    "FUTURES_NIGHT_SESSIONS",
    "NautilusOrderGateway",
    "RebalancePlan",
    "StrategyAdapter",
    "SubmitResult",
    "TradingSession",
    "PriceLimitFillModel",
    "build_equity_engine",
    "day_bar_spec",
    "equity_instrument",
    "futures_contract",
    "in_sessions",
    "is_night_session",
    "minute_bar_spec",
    "run_engine",
    "to_nautilus_bar",
    "to_nautilus_bars",
]
