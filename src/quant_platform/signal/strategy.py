"""共享信号执行器 SignalStrategy。

这是「管道统一」的核心：bar 订阅、算子构建/喂值、ctx 组装、目标仓位调仓、
保护单（止损/止盈）执行、仓位/均价/持仓时长/止损价跟踪，全部收归平台。
agent 只提供 ``SignalSpec``（声明式指标 + compute_signal 纯函数）。

回测 / paper / 实盘三处加载同一执行器。因子回测的 target-only 信号是本类的
退化用法（只填 target_qty，无保护单）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar as NautilusBar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy

from quant_platform.signal.contract import Signal, SignalSpec
from quant_platform.signal.operators import Operator, build_operator


@dataclass(frozen=True)
class BarView:
    """信号侧看到的 bar（纯数据，不暴露 NT 对象）。"""

    open: float
    high: float
    low: float
    close: float
    volume: float
    ts: str


def _bar_view(bar: NautilusBar) -> BarView:
    return BarView(
        open=float(bar.open.as_double()),
        high=float(bar.high.as_double()),
        low=float(bar.low.as_double()),
        close=float(bar.close.as_double()),
        volume=float(bar.volume.as_double()),
        ts=datetime.fromtimestamp(bar.ts_event / 1e9, tz=UTC).isoformat(),
    )


def _snapshot(ops: dict[str, Operator]) -> SimpleNamespace:
    return SimpleNamespace(
        **{key: SimpleNamespace(**op.snapshot()) for key, op in ops.items()}
    )


class SignalStrategy(Strategy):  # type: ignore[misc]  # Strategy 为 C 扩展
    def __init__(
        self,
        config: StrategyConfig,
        *,
        instrument_id: str,
        bar_type_str: str,
        spec: SignalSpec,
        trend_bar_type_str: str | None = None,
    ) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(instrument_id)
        self._bar_type = BarType.from_str(bar_type_str)
        self._trend_bar_type = (
            BarType.from_str(trend_bar_type_str) if trend_bar_type_str else None
        )
        self._spec = spec

        self._exec_ops: dict[str, Operator] = {
            item["key"]: build_operator(item) for item in spec.indicators
        }
        self._trend_ops: dict[str, Operator] = (
            {item["key"]: build_operator(item) for item in spec.indicators}
            if self._trend_bar_type is not None
            else {}
        )

        self._cur_exec: dict[str, dict[str, float]] = {}
        self._prev_exec: dict[str, dict[str, float]] = {}
        self._cur_trend: dict[str, dict[str, float]] = {}
        self._prev_trend: dict[str, dict[str, float]] = {}
        self._trend_bar_view: BarView | None = None

        self._last_target = 0
        self._entry_price: float | None = None
        self._bars_since_entry = 0
        self._stop_price: float | None = None
        self._take_profit: float | None = None

    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)
        if self._trend_bar_type is not None:
            self.subscribe_bars(self._trend_bar_type)

    def on_bar(self, bar: NautilusBar) -> None:
        if self._trend_bar_type is not None and bar.bar_type == self._trend_bar_type:
            self._prev_trend = self._cur_trend
            for op in self._trend_ops.values():
                op.update(
                    high=float(bar.high.as_double()),
                    low=float(bar.low.as_double()),
                    close=float(bar.close.as_double()),
                )
            self._cur_trend = {
                key: op.snapshot() for key, op in self._trend_ops.items()
            }
            self._trend_bar_view = _bar_view(bar)
            return
        if bar.bar_type != self._bar_type:
            return

        self._prev_exec = self._cur_exec
        for op in self._exec_ops.values():
            op.update(
                high=float(bar.high.as_double()),
                low=float(bar.low.as_double()),
                close=float(bar.close.as_double()),
            )
        self._cur_exec = {key: op.snapshot() for key, op in self._exec_ops.items()}

        ctx = SimpleNamespace(
            bar=_bar_view(bar),
            trend_bar=self._trend_bar_view,
            exec=_snapshot(self._exec_ops),
            trend=_snapshot(self._trend_ops),
            prev=SimpleNamespace(
                exec=SimpleNamespace(
                    **{
                        key: SimpleNamespace(**fields)
                        for key, fields in self._prev_exec.items()
                    }
                ),
                trend=SimpleNamespace(
                    **{
                        key: SimpleNamespace(**fields)
                        for key, fields in self._prev_trend.items()
                    }
                ),
            ),
            position=self._last_target,
            entry_price=self._entry_price,
            bars_since_entry=self._bars_since_entry,
            stop_price=self._stop_price,
            ready=self._all_initialized(),
        )
        signal = self._spec.compute_signal(ctx)
        self._apply_signal(signal, bar)

    def _all_initialized(self) -> bool:
        return all(op.initialized for op in self._exec_ops.values()) and all(
            op.initialized for op in self._trend_ops.values()
        )

    def _apply_signal(self, signal: Signal, bar: NautilusBar) -> None:
        target = int(signal.target_qty)
        if target != self._last_target:
            self._submit_delta(target - self._last_target)
            if self._last_target == 0 and target != 0:
                self._entry_price = float(bar.close.as_double())
                self._bars_since_entry = 0
            elif target == 0:
                self._entry_price = None
                self._bars_since_entry = 0
            self._last_target = target

        if signal.stop_price is not None:
            self._stop_price = signal.stop_price
        if signal.take_profit is not None:
            self._take_profit = signal.take_profit

        if self._last_target != 0:
            self._enforce_protection(bar)
            self._bars_since_entry += 1

    def _submit_delta(self, delta: int) -> None:
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

    def _enforce_protection(self, bar: NautilusBar) -> None:
        high = float(bar.high.as_double())
        low = float(bar.low.as_double())
        long_stop = self._last_target > 0 and (
            (self._stop_price is not None and low <= self._stop_price)
            or (self._take_profit is not None and high >= self._take_profit)
        )
        short_stop = self._last_target < 0 and (
            (self._stop_price is not None and high >= self._stop_price)
            or (self._take_profit is not None and low <= self._take_profit)
        )
        if long_stop or short_stop:
            self._flatten()

    def _flatten(self) -> None:
        self._submit_delta(-self._last_target)
        self._last_target = 0
        self._entry_price = None
        self._bars_since_entry = 0
        self._stop_price = None
        self._take_profit = None

    @property
    def last_target(self) -> int:
        return self._last_target
