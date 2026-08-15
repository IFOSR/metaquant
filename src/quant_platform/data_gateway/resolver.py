"""数据源门面：统一量价契约 + 用户无感的自动 fallback（G17, FR-303/306）。

对上层（因子、回测）只暴露一个 ``MarketDataSourceResolver``。它按配置的
优先级链逐个尝试数据源：主源异常或数据不足就静默切到下一个，最终全部失败
才抛出异常。每个返回都携带 ``quality_issues``（哪些源失败过、为什么），供
审计和观测，但调用方无需感知切换。

期货优先（双边多空），股票次之，但切换逻辑对资产类型是同一套。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    extra: Mapping[str, float] = MappingProxyType({})

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("bar timestamp must be timezone-aware")
        for value in (self.open, self.high, self.low, self.close, self.volume):
            if value < 0:
                raise ValueError("bar fields must be non-negative")
        if self.high < self.low:
            raise ValueError("high must not be below low")


@dataclass(frozen=True, slots=True)
class BarRequest:
    asset_type: str  # "futures" | "stock"
    symbol: str
    timeframe: str  # "1m" | "5m" | "1d"
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.asset_type not in {"futures", "stock"}:
            raise ValueError("asset_type must be futures or stock")
        if not self.symbol or self.symbol.strip() != self.symbol:
            raise ValueError("symbol must be a non-empty normalized identifier")
        if self.timeframe not in {"1m", "5m", "15m", "30m", "60m", "1d"}:
            raise ValueError("unsupported timeframe")
        if self.end <= self.start:
            raise ValueError("end must be after start")


@dataclass(frozen=True, slots=True)
class BarSeries:
    request: BarRequest
    bars: tuple[Bar, ...]
    source_id: str
    quality_issues: tuple[str, ...] = ()

    def is_sufficient(self, min_bars: int) -> bool:
        return len(self.bars) >= min_bars

    def with_quality_issues(self, issues: tuple[str, ...]) -> BarSeries:
        return replace(self, quality_issues=issues)

    def payload(self) -> dict[str, object]:
        return {
            "symbol": self.request.symbol,
            "timeframe": self.request.timeframe,
            "source_id": self.source_id,
            "quality_issues": list(self.quality_issues),
            "bar_count": len(self.bars),
        }


class MarketDataProvider(Protocol):
    source_id: str

    def fetch(self, request: BarRequest) -> BarSeries | None: ...


class DataSourceExhausted(RuntimeError):
    def __init__(self, request: BarRequest, issues: tuple[str, ...]) -> None:
        self.request = request
        self.issues = issues
        joined = "; ".join(issues) if issues else "no providers configured"
        super().__init__(f"all data sources failed for {request.symbol}: {joined}")


class MarketDataSourceResolver:
    """优先级链上的自动 fallback，用户无感。"""

    def __init__(self, providers: tuple[MarketDataProvider, ...]) -> None:
        if not providers:
            raise ValueError("providers must not be empty")
        self.providers = providers

    def fetch(self, request: BarRequest, *, min_bars: int = 1) -> BarSeries:
        issues: list[str] = []
        for provider in self.providers:
            try:
                series = provider.fetch(request)
            except Exception as exc:  # noqa: BLE001 - fallback boundary
                issues.append(f"{provider.source_id}:{type(exc).__name__}")
                continue
            if series is None or not series.is_sufficient(min_bars):
                issues.append(f"{provider.source_id}:insufficient")
                continue
            return series.with_quality_issues(tuple(issues))
        raise DataSourceExhausted(request, tuple(issues))


def default_provider_chain(
    *,
    akshare_module: object | None = None,
    ifind_client: object | None = None,
) -> MarketDataSourceResolver:
    """构建默认优先级链：AKShare → iFinD。"""
    from quant_platform.data_gateway.akshare_vendor import (
        AkShareMarketDataProvider,
    )
    from quant_platform.data_gateway.ifind_client import IFindMarketDataProvider

    providers: list[MarketDataProvider] = [
        AkShareMarketDataProvider(module=akshare_module),
    ]
    if ifind_client is not None:
        from quant_platform.data_gateway.ifind_client import IFindClient

        assert isinstance(ifind_client, IFindClient)
        providers.append(IFindMarketDataProvider(client=ifind_client))
    return MarketDataSourceResolver(tuple(providers))


def resample_bars(bars: tuple[Bar, ...], *, minutes: int) -> tuple[Bar, ...]:
    """将细粒度 bar 合成为 ``minutes`` 分钟 bar（OHLCV 聚合）。

    这是平台的标准能力：策略通常从 1 分钟量价合成 5/10/15 分钟 bar 再决策，
    而不是逐分钟决策。合成规则：open 取桶内首根 bar、high/low 取桶内极值、
    close 取桶内末根 bar、volume 求和、时间戳取桶内末根 bar 的时间。
    """
    if not bars:
        return ()
    if minutes < 1:
        raise ValueError("minutes must be positive")
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    buckets: list[list[Bar]] = []
    current_key: int | None = None
    for bar in ordered:
        # bar 时间戳是终点；分钟向上取整到 minutes 的倍数（跨小时安全）。
        key = (bar.timestamp.hour * 60 + bar.timestamp.minute + minutes - 1) // minutes
        if current_key is None or key != current_key:
            buckets.append([])
            current_key = key
        buckets[-1].append(bar)
    return tuple(_aggregate_bucket(bucket) for bucket in buckets)


def _aggregate_bucket(bucket: list[Bar]) -> Bar:
    first = bucket[0]
    last = bucket[-1]
    extra: dict[str, float] = {}
    for key in ("hold", "settle", "amount"):
        values = [bar.extra[key] for bar in bucket if key in bar.extra]
        if values:
            extra[key] = values[-1]
    return Bar(
        timestamp=last.timestamp,
        open=first.open,
        high=max(bar.high for bar in bucket),
        low=min(bar.low for bar in bucket),
        close=last.close,
        volume=sum(bar.volume for bar in bucket),
        extra=extra,
    )
