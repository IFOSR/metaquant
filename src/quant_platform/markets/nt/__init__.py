"""NautilusTrader 适配层（G18）。

把 ``markets/`` 的规则建模（唯一事实源）映射到 NautilusTrader 的
Instrument / 数据 / 回测 / 执行。
"""

from quant_platform.markets.nt.backtest import (
    backtest_hash,
    build_equity_engine,
    build_futures_engine,
    run_engine,
)
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
from quant_platform.markets.nt.futures_fee import (
    FuturesFeeModel,
    close_offset_fee,
    offset_from_order,
)
from quant_platform.markets.nt.golden import (
    GoldenVerdict,
    build_roll_from_main,
    verify_cn_a_case,
    verify_futures_case,
    verify_golden_cases,
)
from quant_platform.markets.nt.instruments import (
    equity_instrument,
    futures_contract,
)
from quant_platform.markets.nt.liquidation import LiquidationResult, check_margin_call
from quant_platform.markets.nt.roll import RollTransition, build_roll_transitions
from quant_platform.markets.nt.sessions import (
    A_SHARE_SESSIONS,
    FUTURES_DAY_SESSIONS,
    FUTURES_NIGHT_SESSIONS,
    TradingSession,
    in_sessions,
    is_night_session,
)
from quant_platform.markets.nt.settlement import (
    DailySettlement,
    SettlementLeg,
    settle_daily,
)
from quant_platform.markets.nt.strategy import TargetPositionStrategy
from quant_platform.markets.nt.strategy_adapter import (
    RebalancePlan,
    StrategyAdapter,
)

__all__ = [
    "A_SHARE_SESSIONS",
    "AShareFeeModel",
    "DailySettlement",
    "FUTURES_DAY_SESSIONS",
    "FUTURES_NIGHT_SESSIONS",
    "FuturesFeeModel",
    "GoldenVerdict",
    "LiquidationResult",
    "NautilusOrderGateway",
    "PriceLimitFillModel",
    "RebalancePlan",
    "RollTransition",
    "SettlementLeg",
    "StrategyAdapter",
    "SubmitResult",
    "TradingSession",
    "TargetPositionStrategy",
    "backtest_hash",
    "build_equity_engine",
    "build_futures_engine",
    "build_roll_from_main",
    "build_roll_transitions",
    "check_margin_call",
    "close_offset_fee",
    "day_bar_spec",
    "equity_instrument",
    "futures_contract",
    "in_sessions",
    "is_night_session",
    "minute_bar_spec",
    "offset_from_order",
    "run_engine",
    "settle_daily",
    "to_nautilus_bar",
    "to_nautilus_bars",
    "verify_cn_a_case",
    "verify_futures_case",
    "verify_golden_cases",
]
