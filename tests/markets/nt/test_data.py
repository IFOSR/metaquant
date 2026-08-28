from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from quant_platform.data_gateway.resolver import Bar
from quant_platform.markets.nt.data import (
    day_bar_spec,
    minute_bar_spec,
    to_nautilus_bar,
    to_nautilus_bars,
)
from quant_platform.markets.nt.instruments import equity_instrument

SHANGHAI = ZoneInfo("Asia/Shanghai")


def sample_bar(minute: int) -> Bar:
    return Bar(
        timestamp=datetime(2026, 8, 14, 9, minute, tzinfo=SHANGHAI),
        open=10.0,
        high=10.5,
        low=9.5,
        close=10.2,
        volume=1000.0,
    )


def test_minute_bar_spec_step() -> None:
    spec = minute_bar_spec(5)

    assert spec.step == 5


def test_minute_bar_spec_60m_maps_to_hour() -> None:
    """60 分钟归一到 1-HOUR（NautilusTrader 不允许 MINUTE step=60）。"""
    from nautilus_trader.model.enums import BarAggregation

    spec = minute_bar_spec(60)
    assert spec.step == 1
    assert spec.aggregation == BarAggregation.HOUR


def test_day_bar_spec() -> None:
    spec = day_bar_spec()

    assert spec.step == 1


def test_to_nautilus_bar_converts_ohlcv() -> None:
    instrument = equity_instrument(symbol="600000")
    converted = to_nautilus_bar(
        sample_bar(35),
        instrument_id=instrument.id,
        bar_spec=minute_bar_spec(5),
        price_precision=2,
    )

    assert converted.open.as_double() == 10.0
    assert converted.high.as_double() == 10.5
    assert converted.low.as_double() == 9.5
    assert converted.close.as_double() == 10.2
    assert converted.volume.as_double() == 1000.0
    assert converted.bar_type.instrument_id == instrument.id


def test_to_nautilus_bars_sorts_by_timestamp() -> None:
    instrument = equity_instrument(symbol="600000")
    bars = (sample_bar(36), sample_bar(35))  # 乱序输入

    converted = to_nautilus_bars(
        bars,
        instrument_id=instrument.id,
        bar_spec=minute_bar_spec(5),
        price_precision=2,
    )

    assert converted[0].ts_event < converted[1].ts_event


def test_bar_ts_init_equals_ts_event_close() -> None:
    """对齐 NT 交互：bar 的 ts_init 必须等于区间收盘（ts_event）。

    撮合时点以 ts_init 为准；PIT 的 event_time 就是收盘时点（日线 15:00、
    分钟级 bar 收盘），ts_init 不能滞后否则撮合发生在错误时点。
    """
    instrument = equity_instrument(symbol="600000")
    converted = to_nautilus_bar(
        sample_bar(35),
        instrument_id=instrument.id,
        bar_spec=minute_bar_spec(5),
        price_precision=2,
    )
    assert converted.ts_init == converted.ts_event
    expected_ns = int(sample_bar(35).timestamp.timestamp() * 1_000_000_000)
    assert converted.ts_event == expected_ns


def test_price_precision_validation() -> None:
    instrument = equity_instrument(symbol="600000")

    with pytest.raises(ValueError):
        to_nautilus_bar(
            sample_bar(35),
            instrument_id=instrument.id,
            bar_spec=minute_bar_spec(5),
            price_precision=-1,
        )
