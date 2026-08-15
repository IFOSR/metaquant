from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from quant_platform.data_gateway.resolver import (
    Bar,
    BarRequest,
    BarSeries,
    DataSourceExhausted,
    MarketDataSourceResolver,
    assign_trading_dates,
    resample_bars,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def request() -> BarRequest:
    return BarRequest(
        asset_type="futures",
        symbol="RB2610",
        timeframe="5m",
        start=datetime(2026, 8, 14, 9, 0, tzinfo=SHANGHAI),
        end=datetime(2026, 8, 14, 15, 0, tzinfo=SHANGHAI),
    )


def bar(hour: int) -> Bar:
    return Bar(
        timestamp=datetime(2026, 8, 14, hour, 0, tzinfo=SHANGHAI),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100.0,
    )


def series(source_id: str, count: int) -> BarSeries:
    return BarSeries(
        request=request(),
        bars=tuple(bar(9 + index) for index in range(count)),
        source_id=source_id,
    )


class FakeProvider:
    def __init__(self, source_id: str, result: object) -> None:
        self.source_id = source_id
        self.result = result

    def fetch(self, req: BarRequest) -> BarSeries | None:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result  # type: ignore[return-value]


def test_primary_source_wins() -> None:
    resolver = MarketDataSourceResolver(
        (FakeProvider("a", series("a", 5)), FakeProvider("b", series("b", 5)))
    )

    result = resolver.fetch(request())

    assert result.source_id == "a"
    assert result.quality_issues == ()


def test_fallback_on_exception() -> None:
    resolver = MarketDataSourceResolver(
        (
            FakeProvider("a", RuntimeError("boom")),
            FakeProvider("b", series("b", 5)),
        )
    )

    result = resolver.fetch(request())

    assert result.source_id == "b"
    assert result.quality_issues == ("a:RuntimeError",)


def test_fallback_on_insufficient() -> None:
    resolver = MarketDataSourceResolver(
        (FakeProvider("a", series("a", 0)), FakeProvider("b", series("b", 5)))
    )

    result = resolver.fetch(request(), min_bars=3)

    assert result.source_id == "b"
    assert result.quality_issues == ("a:insufficient",)


def test_all_sources_exhausted() -> None:
    resolver = MarketDataSourceResolver(
        (
            FakeProvider("a", RuntimeError("boom")),
            FakeProvider("b", series("b", 0)),
        )
    )

    with pytest.raises(DataSourceExhausted) as exc:
        resolver.fetch(request(), min_bars=1)

    assert exc.value.issues == ("a:RuntimeError", "b:insufficient")


def test_providers_must_not_be_empty() -> None:
    with pytest.raises(ValueError):
        MarketDataSourceResolver(())


def test_bar_request_validation() -> None:
    with pytest.raises(ValueError, match="asset_type"):
        BarRequest(
            asset_type="forex",
            symbol="EURUSD",
            timeframe="1m",
            start=datetime(2026, 8, 14, tzinfo=SHANGHAI),
            end=datetime(2026, 8, 15, tzinfo=SHANGHAI),
        )


def minute_bars() -> tuple[Bar, ...]:
    # 09:31..09:42，12 根 1 分钟 bar
    bars: list[Bar] = []
    for offset in range(12):
        minute = 31 + offset
        bars.append(
            Bar(
                timestamp=datetime(2026, 8, 14, 9, minute, tzinfo=SHANGHAI),
                open=float(offset),
                high=float(offset + 10),
                low=float(offset),
                close=float(offset + 1),
                volume=float(100 + offset),
            )
        )
    return tuple(bars)


def test_resample_5m_bars_aggregates_ohlcv() -> None:
    resampled = resample_bars(minute_bars(), minutes=5)

    # 12 根 1 分钟 → 3 桶（09:31-09:35、09:36-09:40、09:41-09:42）
    assert len(resampled) == 3
    first = resampled[0]
    assert first.timestamp.minute == 35
    assert first.open == 0.0
    assert first.close == 5.0
    assert first.high == 14.0  # max(offset+10) for offset 0..4
    assert first.low == 0.0  # min(offset)
    assert first.volume == 510.0  # sum(100..104)


def test_resample_empty_bars() -> None:
    assert resample_bars((), minutes=5) == ()


def test_resample_rejects_nonpositive_minutes() -> None:
    with pytest.raises(ValueError, match="minutes"):
        resample_bars(minute_bars(), minutes=0)


def test_resample_preserves_extra_fields() -> None:
    bars = (
        Bar(
            timestamp=datetime(2026, 8, 14, 9, 31, tzinfo=SHANGHAI),
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=10.0,
            extra={"hold": 100.0},
        ),
        Bar(
            timestamp=datetime(2026, 8, 14, 9, 32, tzinfo=SHANGHAI),
            open=1.5,
            high=2.5,
            low=1.0,
            close=2.0,
            volume=20.0,
            extra={"hold": 200.0},
        ),
    )

    resampled = resample_bars(bars, minutes=5)

    assert len(resampled) == 1
    assert resampled[0].extra["hold"] == 200.0  # 末根 bar 的 hold


def night_bar(hour: int) -> Bar:
    return Bar(
        timestamp=datetime(2026, 8, 14, hour, 0, tzinfo=SHANGHAI),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=10.0,
    )


def test_assign_day_session_bar_to_same_day() -> None:
    calendar = (date(2026, 8, 14), date(2026, 8, 17), date(2026, 8, 18))

    assigned = assign_trading_dates((night_bar(14),), calendar)

    assert assigned[0].trading_date == date(2026, 8, 14)


def test_assign_night_session_bar_to_next_trading_day() -> None:
    calendar = (date(2026, 8, 14), date(2026, 8, 17), date(2026, 8, 18))

    assigned = assign_trading_dates((night_bar(21),), calendar)

    assert assigned[0].trading_date == date(2026, 8, 17)


def test_assign_night_session_skips_weekend() -> None:
    # 周五 21:00 夜盘，下一个交易日是周一（跳过周末）
    calendar = (date(2026, 8, 14), date(2026, 8, 17))

    assigned = assign_trading_dates((night_bar(21),), calendar)

    assert assigned[0].trading_date == date(2026, 8, 17)


def test_resample_preserves_trading_date() -> None:
    calendar = (date(2026, 8, 14), date(2026, 8, 17))
    bar1 = Bar(
        timestamp=datetime(2026, 8, 14, 20, 59, tzinfo=SHANGHAI),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=10.0,
    )
    bar2 = Bar(
        timestamp=datetime(2026, 8, 14, 21, 0, tzinfo=SHANGHAI),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=10.0,
    )
    night_bars = assign_trading_dates((bar1, bar2), calendar)

    resampled = resample_bars(night_bars, minutes=5)

    assert len(resampled) == 1
    assert resampled[0].trading_date == date(2026, 8, 17)


def test_assign_requires_calendar() -> None:
    with pytest.raises(ValueError, match="trading_dates"):
        assign_trading_dates((night_bar(14),), ())
