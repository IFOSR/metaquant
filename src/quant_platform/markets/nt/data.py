"""数据转换：data_gateway 的 Bar → NautilusTrader Bar（G18 P1）。

这是 PIT → NautilusTrader 数据流的映射层。我们的 ``Bar``（统一量价契约）
转成 NautilusTrader 的 ``Bar``（bar_type + Price/Quantity + 纳秒时间戳），
供 BacktestEngine / DataEngine 消费。
"""

from __future__ import annotations

from nautilus_trader.model.data import Bar as NautilusBar
from nautilus_trader.model.data import BarSpecification, BarType
from nautilus_trader.model.enums import BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from quant_platform.data_gateway.resolver import Bar


def minute_bar_spec(step: int) -> BarSpecification:
    """N 分钟 bar 规格（step=5 即 5 分钟；step=60 归一到 1 小时）。"""
    if step < 1:
        raise ValueError("step must be positive")
    if step == 60:
        # NautilusTrader 不允许 MINUTE 聚合的 step=60，改用 1-HOUR。
        return BarSpecification(1, BarAggregation.HOUR, PriceType.LAST)
    return BarSpecification(step, BarAggregation.MINUTE, PriceType.LAST)


def day_bar_spec() -> BarSpecification:
    """日频 bar 规格。"""
    return BarSpecification(1, BarAggregation.DAY, PriceType.LAST)


def _as_instrument_id(instrument_id: InstrumentId | str) -> InstrumentId:
    """兼容传入 NT ``InstrumentId`` 或字符串（如 ``RB2610.SHFE``）。"""
    return (
        instrument_id
        if isinstance(instrument_id, InstrumentId)
        else InstrumentId.from_str(instrument_id)
    )


def to_nautilus_bar(
    bar: Bar,
    *,
    instrument_id: InstrumentId | str,
    bar_spec: BarSpecification,
    price_precision: int,
) -> NautilusBar:
    """把我们的 Bar 转成 NautilusTrader Bar。"""
    if price_precision < 0:
        raise ValueError("price_precision must be non-negative")
    ts_ns = int(bar.timestamp.timestamp() * 1_000_000_000)
    return NautilusBar(
        bar_type=BarType(_as_instrument_id(instrument_id), bar_spec),
        open=Price(bar.open, price_precision),
        high=Price(bar.high, price_precision),
        low=Price(bar.low, price_precision),
        close=Price(bar.close, price_precision),
        volume=Quantity(bar.volume, 0),
        ts_event=ts_ns,
        ts_init=ts_ns,
    )


def to_nautilus_bars(
    bars: tuple[Bar, ...],
    *,
    instrument_id: InstrumentId | str,
    bar_spec: BarSpecification,
    price_precision: int,
) -> list[NautilusBar]:
    """批量转换，按时间戳升序。"""
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    return [
        to_nautilus_bar(
            bar,
            instrument_id=instrument_id,
            bar_spec=bar_spec,
            price_precision=price_precision,
        )
        for bar in ordered
    ]
