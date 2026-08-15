"""NautilusTrader 适配层（G18）。

把 ``markets/`` 的规则建模（唯一事实源）映射到 NautilusTrader 的
Instrument / 数据 / 回测 / 执行。
"""

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

__all__ = [
    "A_SHARE_SESSIONS",
    "FUTURES_DAY_SESSIONS",
    "FUTURES_NIGHT_SESSIONS",
    "TradingSession",
    "equity_instrument",
    "futures_contract",
    "in_sessions",
    "is_night_session",
]
