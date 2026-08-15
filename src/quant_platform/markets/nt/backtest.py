"""NautilusTrader 回测装配（G18 P2）。

低层 ``BacktestEngine.add_venue()`` 装配，供后续中国市场撮合适配（P3）在
此基础上叠加自定义 FillModel/FeeModel/结算组件。P2 阶段只保证端到端
smoke 跑通，不承诺执行语义正确性。
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.currencies import CNY
from nautilus_trader.model.data import Bar as NautilusBar
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Money


def build_equity_engine(
    *,
    instrument: Equity,
    initial_cash: Decimal,
    venue: str = "SSE",
) -> BacktestEngine:
    """装配 A 股现金账户回测引擎（NETTING + CASH）。"""
    engine = BacktestEngine()
    engine.add_venue(
        venue=Venue(venue),
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        starting_balances=[Money(initial_cash, CNY)],
    )
    engine.add_instrument(instrument)
    return engine


def run_engine(
    engine: BacktestEngine,
    *,
    bars: list[NautilusBar],
) -> None:
    """喂数据并跑回测。"""
    engine.add_data(bars)
    engine.run()
