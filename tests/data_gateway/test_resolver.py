from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from quant_platform.data_gateway.resolver import (
    Bar,
    BarRequest,
    BarSeries,
    DataSourceExhausted,
    MarketDataSourceResolver,
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
