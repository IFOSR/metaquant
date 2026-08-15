from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from nautilus_trader.config import StrategyConfig

from quant_platform.data_gateway.resolver import Bar
from quant_platform.markets.nt.backtest import build_equity_engine
from quant_platform.markets.nt.data import minute_bar_spec, to_nautilus_bar
from quant_platform.markets.nt.instruments import equity_instrument
from quant_platform.markets.nt.strategy import TargetPositionStrategy

SHANGHAI = ZoneInfo("Asia/Shanghai")


def bar(hour: int, minute: int, close: float) -> Bar:
    return Bar(
        timestamp=datetime(2026, 8, 14, hour, minute, tzinfo=SHANGHAI),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
    )


def test_end_to_end_strategy_buys_and_holds() -> None:
    instrument = equity_instrument(symbol="600000")
    engine = build_equity_engine(instrument=instrument, initial_cash=Decimal("100000"))

    bar_type_str = f"{instrument.id}-1-MINUTE-LAST-EXTERNAL"
    strategy = TargetPositionStrategy(
        StrategyConfig(strategy_id="S-001"),
        instrument_id=str(instrument.id),
        target_qty_fn=lambda _bar: 100,
        bar_type_str=bar_type_str,
    )
    engine.add_strategy(strategy)

    bars = [
        to_nautilus_bar(
            bar(9, 31, 10.0),
            instrument_id=instrument.id,
            bar_spec=minute_bar_spec(1),
            price_precision=2,
        ),
        to_nautilus_bar(
            bar(9, 32, 10.5),
            instrument_id=instrument.id,
            bar_spec=minute_bar_spec(1),
            price_precision=2,
        ),
    ]
    engine.add_data(bars)
    engine.run()

    # 目标 100 股：首根 bar 下单买入，第二根 bar 目标仍为 100（无增量）
    assert strategy.last_target == 100
    fills = engine.trader.generate_order_fills_report()
    assert len(fills) > 0
    positions = engine.trader.generate_positions_report()
    assert len(positions) > 0
