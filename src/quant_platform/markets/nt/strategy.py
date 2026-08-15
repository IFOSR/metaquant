"""NautilusTrader 目标仓位策略 (G18-P6)。

把 StrategyAdapter 的目标仓位决策接入 NautilusTrader 事件循环：``on_bar``
回调里调用目标仓位函数，与当前目标仓位比较后产生调仓市价单。回测与
paper/live 共用同一份策略代码（``TargetPositionStrategy``），消除偏差。
"""

from __future__ import annotations

from collections.abc import Callable

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar as NautilusBar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy

TargetQtyFn = Callable[[NautilusBar], int]


class TargetPositionStrategy(Strategy):  # type: ignore[misc]  # Strategy 为 C 扩展
    """按目标仓位函数调仓的策略。

    每次 ``on_bar`` 用 ``target_qty_fn`` 计算目标持仓数量，与上次目标比较，
    差异即为调仓量。策略自身跟踪上次目标，避免依赖运行时持仓查询。
    """

    def __init__(
        self,
        config: StrategyConfig,
        *,
        instrument_id: str,
        target_qty_fn: TargetQtyFn,
        bar_type_str: str,
    ) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(instrument_id)
        self._target_qty_fn = target_qty_fn
        self._bar_type = BarType.from_str(bar_type_str)
        self._last_target = 0

    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)

    def on_bar(self, bar: NautilusBar) -> None:
        target = self._target_qty_fn(bar)
        delta = target - self._last_target
        self._last_target = target
        if delta == 0:
            return
        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        instrument = self.cache.instrument(self._instrument_id)
        if instrument is None:
            return
        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=side,
            quantity=instrument.make_qty(abs(delta)),
        )
        self.submit_order(order)

    @property
    def last_target(self) -> int:
        return self._last_target
