"""NautilusTrader 回测装配（G18 P2）。

低层 ``BacktestEngine.add_venue()`` 装配，供后续中国市场撮合适配（P3）在
此基础上叠加自定义 FillModel/FeeModel/结算组件。P2 阶段只保证端到端
smoke 跑通，不承诺执行语义正确性。
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import FeeModel, FillModel
from nautilus_trader.model.currencies import CNY
from nautilus_trader.model.data import Bar as NautilusBar
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import Equity, FuturesContract
from nautilus_trader.model.objects import Money

from quant_platform.experiments import canonical_hash
from quant_platform.markets.nt.venue import VenueSpec


def _venue_add(
    engine: BacktestEngine,
    *,
    venue: str,
    oms_type: OmsType,
    account_type: AccountType,
    initial_cash: Decimal,
    venue_spec: VenueSpec | None,
    fee_model: FeeModel | None,
    fill_model: FillModel | None,
) -> None:
    """把执行假设落到 ``add_venue``：venue_spec 优先（对齐 NT 交互），旧签名兼容。"""
    engine.add_venue(
        venue=Venue(venue),
        oms_type=oms_type,
        account_type=account_type,
        starting_balances=[Money(initial_cash, CNY)],
        fee_model=(venue_spec.fee_model if venue_spec is not None else fee_model),
        fill_model=(venue_spec.fill_model if venue_spec is not None else fill_model),
        latency_model=venue_spec.latency_model if venue_spec is not None else None,
        price_protection_points=(
            venue_spec.price_protection_points if venue_spec is not None else None
        ),
    )


def build_equity_engine(
    *,
    instrument: Equity,
    initial_cash: Decimal,
    venue: str = "SSE",
    fee_model: FeeModel | None = None,
    fill_model: FillModel | None = None,
    venue_spec: VenueSpec | None = None,
) -> BacktestEngine:
    """装配 A 股现金账户回测引擎（NETTING + CASH）。

    ``venue_spec`` 为完整执行假设（费用/撮合/延迟/价格保护，对齐 NT 交互）；
    提供时优先于 ``fee_model``/``fill_model`` 单项参数（旧签名兼容）。
    缺省为 None 时保持 NautilusTrader 默认行为，调用方必须在结果披露中标注成本口径。
    """
    engine = BacktestEngine()
    _venue_add(
        engine,
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        initial_cash=initial_cash,
        venue_spec=venue_spec,
        fee_model=fee_model,
        fill_model=fill_model,
    )
    engine.add_instrument(instrument)
    return engine


def backtest_hash(engine: BacktestEngine) -> str:
    """回测结果的内容寻址 hash（验收门禁 2 确定性 replay）。

    只投影确定性的业务字段，排除 NautilusTrader 内部每次运行随机生成的
    UUID（``init_id``/``venue_order_id``）与时间戳，使相同输入的两次回测
    产生相同 hash。
    """
    fills = engine.trader.generate_order_fills_report()
    positions = engine.trader.generate_positions_report()
    fill_records = [
        {
            "instrument_id": row["instrument_id"],
            "side": row["side"],
            "quantity": str(row["quantity"]),
            "filled_qty": str(row["filled_qty"]),
            "avg_px": float(row["avg_px"]),
            "commissions": list(row["commissions"]),
        }
        for _, row in fills.iterrows()
    ]
    position_records = [
        {
            "instrument_id": row["instrument_id"],
            "entry": row["entry"],
            "side": row["side"],
            "quantity": str(row["quantity"]),
            "avg_px_open": float(row["avg_px_open"]),
            "realized_pnl": str(row["realized_pnl"]),
        }
        for _, row in positions.iterrows()
    ]
    payload: dict[str, object] = {
        "fills": fill_records,
        "positions": position_records,
    }
    return canonical_hash(payload)


def run_engine(
    engine: BacktestEngine,
    *,
    bars: list[NautilusBar],
) -> None:
    """喂数据并跑回测。"""
    engine.add_data(bars)
    engine.run()


def build_futures_engine(
    *,
    instrument: FuturesContract,
    initial_cash: Decimal,
    venue: str = "SHFE",
    fee_model: FeeModel | None = None,
    fill_model: FillModel | None = None,
    venue_spec: VenueSpec | None = None,
) -> BacktestEngine:
    """装配商品期货保证金账户回测引擎（NETTING + MARGIN）。

    费用/撮合模型语义同 :func:`build_equity_engine`。
    """
    engine = BacktestEngine()
    _venue_add(
        engine,
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        initial_cash=initial_cash,
        venue_spec=venue_spec,
        fee_model=fee_model,
        fill_model=fill_model,
    )
    engine.add_instrument(instrument)
    return engine
