from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from quant_platform.data_gateway.resolver import Bar
from quant_platform.markets.nt.backtest import build_equity_engine, run_engine
from quant_platform.markets.nt.data import minute_bar_spec, to_nautilus_bars
from quant_platform.markets.nt.instruments import equity_instrument

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _bars() -> tuple[Bar, ...]:
    return tuple(
        Bar(
            timestamp=datetime(2026, 8, 14, 9, 30 + minute, tzinfo=SHANGHAI),
            open=10.0,
            high=10.5,
            low=9.5,
            close=10.2,
            volume=1000.0,
        )
        for minute in range(1, 5)
    )


def test_equity_engine_smoke() -> None:
    instrument = equity_instrument(symbol="600000")
    engine = build_equity_engine(instrument=instrument, initial_cash=Decimal("1000000"))

    nautilus_bars = to_nautilus_bars(
        _bars(),
        instrument_id=instrument.id,
        bar_spec=minute_bar_spec(5),
        price_precision=2,
    )

    # P2 smoke：只断言端到端跑通，不验证执行语义正确性。
    run_engine(engine, bars=nautilus_bars)

    assert engine.trader is not None
    assert engine.get_result() is not None


def test_equity_engine_no_orders_keeps_balance() -> None:
    instrument = equity_instrument(symbol="600000")
    engine = build_equity_engine(instrument=instrument, initial_cash=Decimal("1000000"))

    nautilus_bars = to_nautilus_bars(
        _bars(),
        instrument_id=instrument.id,
        bar_spec=minute_bar_spec(5),
        price_precision=2,
    )
    run_engine(engine, bars=nautilus_bars)

    # 无订单时账户现金不变（smoke 级校验）。
    account = engine.trader.generate_account_report(instrument.id.venue)
    total = float(account["total"].iloc[-1])
    assert total == 1_000_000.0
