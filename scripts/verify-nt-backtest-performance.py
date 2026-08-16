"""NautilusTrader 回测性能验证 (G18-P6, 验收门禁 3)。

按本轮决策下调规模：A 股用 1–2 只标的验证正确性即可，性能压测聚焦期货
主力合约。本脚本合成 N 个期货主力合约的日频 bar，跑 NautilusTrader
事件驱动回测，记录端到端耗时与吞吐，作为验收门禁 3 的实测证据。
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar as NautilusBar
from nautilus_trader.model.instruments import FuturesContract

from quant_platform.data_gateway.resolver import Bar
from quant_platform.markets.nt.backtest import build_futures_engine
from quant_platform.markets.nt.data import day_bar_spec, to_nautilus_bar
from quant_platform.markets.nt.instruments import futures_contract
from quant_platform.markets.nt.strategy import TargetPositionStrategy

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _synthetic_contract(index: int, end: datetime) -> FuturesContract:
    activation = int((end - timedelta(days=400)).timestamp() * 1_000_000_000)
    expiration = int((end + timedelta(days=120)).timestamp() * 1_000_000_000)
    return futures_contract(
        symbol=f"RB{index:02d}",
        venue="SHFE",
        underlying="RB",
        price_increment="1",
        multiplier="10",
        price_precision=0,
        activation_ns=activation,
        expiration_ns=expiration,
    )


def main() -> None:
    n_contracts = 50
    n_days = 2400  # ~10 年日频

    end = datetime(2026, 8, 15, tzinfo=SHANGHAI)
    engine = build_futures_engine(
        instrument=_synthetic_contract(0, end), initial_cash=Decimal("100_000_000")
    )
    instruments = [_synthetic_contract(0, end)]
    for index in range(1, n_contracts):
        instrument = _synthetic_contract(index, end)
        instruments.append(instrument)
        engine.add_instrument(instrument)

    all_bars: list[NautilusBar] = []
    for instrument in instruments:
        bar_type_str = f"{instrument.id}-1-DAY-LAST-EXTERNAL"
        strategy = TargetPositionStrategy(
            StrategyConfig(strategy_id=f"S-{instrument.id}"),
            instrument_id=str(instrument.id),
            target_qty_fn=lambda _bar: 1,
            bar_type_str=bar_type_str,
        )
        engine.add_strategy(strategy)

        day = end - timedelta(days=n_days)
        for offset in range(n_days):
            bar = Bar(
                timestamp=day + timedelta(days=offset),
                open=3000.0,
                high=3010.0,
                low=2990.0,
                close=3005.0,
                volume=1000.0,
            )
            all_bars.append(
                to_nautilus_bar(
                    bar,
                    instrument_id=instrument.id,
                    bar_spec=day_bar_spec(),
                    price_precision=0,
                )
            )

    engine.add_data(all_bars)
    started = time.perf_counter()
    engine.run()
    elapsed = time.perf_counter() - started

    bar_count = len(all_bars)
    print(f"[性能] 合约数: {n_contracts}")
    print(f"[性能] bar 总数: {bar_count}")
    print(f"[性能] 回测耗时: {elapsed:.2f}s")
    print(f"[性能] 吞吐: {bar_count / elapsed:.0f} bar/s")


if __name__ == "__main__":
    main()
