"""Watermark-based incremental bar polling for paper accounts.

Paper trading consumes data as it arrives, not as a batch. The poller keeps
a per-instrument watermark (last pushed bar timestamp) and fetches only the
bars that appeared since — from the PIT store, exactly like every other
consumer of market data. Frequency is a property of the account's frozen
artifact: ``1d`` reads ``market.eod.*``; ``5m``/``15m``/``30m``/``60m`` read
``market.minute.*`` and aggregate the 5m base to the target frequency.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.config import LiveDataClientConfig
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.live.factories import LiveDataClientFactory
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import ClientId, Venue

from quant_platform.backtest.service import _build_bars
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.data_gateway.resolver import Bar
from quant_platform.strategy_generation.backtest import (
    aggregate_bars,
    db_instrument_id,
)

# 分钟级频率统一以 5m 为基础粒度入库，15/30/60m 由读取侧聚合。
_MINUTE_BASE = "5m"


def field_prefix_for(frequency: str) -> str:
    if frequency == "1d":
        return "market.eod"
    if frequency in ("5m", "15m", "30m", "60m"):
        return "market.minute"
    raise ValueError(f"unsupported frequency: {frequency}")


@dataclass(frozen=True, slots=True)
class PolledBar:
    instrument_id: str  # user-facing id (600000.SH / RB2610.SHF)
    bar: Bar


def load_bars_range(
    *,
    store: SqlAlchemyPitStore,
    instrument_ids: tuple[str, ...],
    frequency: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, list[Bar]]:
    """Load bars for an explicit time range (stateless; poller 与 data client 共用)。"""
    base_granularity = "1d" if frequency == "1d" else _MINUTE_BASE
    field_prefix = field_prefix_for(frequency)
    db_ids = tuple(db_instrument_id(item) for item in instrument_ids)
    rows = store.load(
        instrument_ids=db_ids,
        field_prefix=field_prefix,
        start=start,
        end=end,
    )
    bars_by_db = _build_bars(rows, db_ids, field_prefix)
    result: dict[str, list[Bar]] = {}
    for instrument_id, db_id in zip(instrument_ids, db_ids, strict=True):
        bars = list(bars_by_db.get(db_id, ()))
        if frequency != base_granularity:
            # 15/30/60m：基础粒度（5m）聚合到目标频率。
            bars = list(aggregate_bars(bars, frequency))
        result[instrument_id] = bars
    return result


class PitBarPoller:
    """Fetch bars newer than per-instrument watermarks."""

    def __init__(
        self,
        *,
        store: SqlAlchemyPitStore,
        instrument_ids: tuple[str, ...],
        frequency: str,
        warmup_bars: int = 0,
    ) -> None:
        if not instrument_ids:
            raise ValueError("poller requires at least one instrument")
        self._store = store
        self._instrument_ids = tuple(instrument_ids)
        self._frequency = frequency
        self._base_granularity = "1d" if frequency == "1d" else _MINUTE_BASE
        self._field_prefix = field_prefix_for(frequency)
        self._warmup = max(0, warmup_bars)
        self._watermarks: dict[str, datetime | None] = {
            instrument_id: None for instrument_id in self._instrument_ids
        }
        self._first_poll_done = False

    @property
    def warmed_up(self) -> bool:
        return self._first_poll_done

    def poll(self) -> list[PolledBar]:
        """Return new bars per instrument (oldest first); advance watermarks."""
        bars_by_inst = load_bars_range(
            store=self._store,
            instrument_ids=self._instrument_ids,
            frequency=self._frequency,
        )
        polled: list[PolledBar] = []
        for instrument_id in self._instrument_ids:
            all_bars = bars_by_inst.get(instrument_id, [])
            watermark = self._watermarks[instrument_id]
            if watermark is None:
                # 首轮拉取已被 prime() 取代；未 prime 直接 poll 时保持旧语义：
                # 只推尾部预热窗口，其余历史仅推进水位线。
                fresh = list(all_bars[-self._warmup :]) if self._warmup else []
                if all_bars:
                    self._watermarks[instrument_id] = all_bars[-1].timestamp
            else:
                fresh = [bar for bar in all_bars if bar.timestamp > watermark]
            for bar in fresh:
                polled.append(PolledBar(instrument_id=instrument_id, bar=bar))
            if fresh:
                previous = self._watermarks[instrument_id]
                latest = fresh[-1].timestamp
                self._watermarks[instrument_id] = (
                    latest if previous is None else max(previous, latest)
                )
        self._first_poll_done = True
        return polled

    def prime(self) -> dict[str, datetime | None]:
        """推进水位线到最新 bar，返回每个标的的预热窗口起点。

        预热数据由 NT 的历史数据通道（``request_bars`` →
        ``on_historical_data``）补齐，只喂指标、不产生订单流；水位线提前
        到最新，保证后续 poll 只推真正的新 bar。
        """
        bars_by_inst = load_bars_range(
            store=self._store,
            instrument_ids=self._instrument_ids,
            frequency=self._frequency,
        )
        starts: dict[str, datetime | None] = {}
        for instrument_id in self._instrument_ids:
            all_bars = bars_by_inst.get(instrument_id, [])
            if not all_bars:
                starts[instrument_id] = None
                continue
            window = all_bars[-self._warmup :] if self._warmup else []
            starts[instrument_id] = window[0].timestamp if window else None
            self._watermarks[instrument_id] = all_bars[-1].timestamp
        self._first_poll_done = True
        return starts

    def watermark(self, instrument_id: str) -> datetime | None:
        return self._watermarks.get(instrument_id)


def utc_now() -> datetime:
    return datetime.now(UTC)


# ── NT 原生数据客户端：PIT store 作为 paper 节点的行情源 ─────────────────


class PitDataClientConfig(LiveDataClientConfig):
    """标记配置；store/标的/频率通过工厂类属性注入（create 签名固定）。"""


class PitDataClient(LiveMarketDataClient):
    """以 PIT store 为后端的 live 数据客户端。

    历史请求（``request_bars``）从 PIT 读区间数据，经 ``_handle_bars``
    走 NT 的 DataResponse 通道——送达策略的 ``on_historical_data``，喂指标
    但不产生订单流。实盘 bar 由 runner 轮询后调 :meth:`publish_bar` 推送。
    """

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        client_id: ClientId,
        venue: Venue,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        store: SqlAlchemyPitStore,
        instruments: dict[str, tuple[str, int]],  # NT id → (user id, 价格精度)
        frequency: str,
        bar_spec: Any,
    ) -> None:
        super().__init__(
            loop=loop,
            client_id=client_id,
            venue=venue,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=InstrumentProvider(),
        )
        self._store = store
        self._instruments = instruments
        self._frequency = frequency
        self._bar_spec = bar_spec

    async def _connect(self) -> None:
        # 纯进程内数据源，无外部连接。
        return None

    async def _disconnect(self) -> None:
        return None

    async def _subscribe_bars(self, command: Any) -> None:
        # 订阅登记由基类完成；实盘数据由 runner 轮询推送，无后台流。
        return None

    async def _request_bars(self, request: Any) -> None:
        from quant_platform.markets.nt import to_nautilus_bars

        bar_type: BarType = request.bar_type
        nt_id = str(bar_type.instrument_id)
        if nt_id not in self._instruments:
            self._log.error(f"no PIT mapping for {nt_id}")
            return
        user_id, precision = self._instruments[nt_id]
        loaded = await asyncio.to_thread(
            load_bars_range,
            store=self._store,
            instrument_ids=(user_id,),
            frequency=self._frequency,
            start=request.start,
            end=request.end,
        )
        nt_bars = to_nautilus_bars(
            tuple(loaded.get(user_id, [])),
            instrument_id=nt_id,
            bar_spec=self._bar_spec,
            price_precision=precision,
        )
        self._handle_bars(
            bar_type=bar_type,
            bars=nt_bars,
            correlation_id=request.id,
            start=request.start,
            end=request.end,
            params=request.params,
        )

    def publish_bar(self, bar: Any) -> None:
        """实盘 bar 入口：经 NT 标准数据路径分发（策略/缓存/撮合所）。"""
        self._handle_data(bar)


class PitDataClientFactory(LiveDataClientFactory):
    """工厂：NT 以类注册，实例经类属性回取给 runner。"""

    store: Any = None
    instruments: dict[str, tuple[str, int]] = {}
    frequency: str = "1d"
    bar_spec: Any = None
    instance: PitDataClient | None = None

    @classmethod
    def create(
        cls,
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: LiveDataClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> PitDataClient:
        client = PitDataClient(
            loop=loop,
            client_id=ClientId(name),
            venue=Venue(name),
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            store=cls.store,
            instruments=cls.instruments,
            frequency=cls.frequency,
            bar_spec=cls.bar_spec,
        )
        cls.instance = client
        return client


def data_factory_for(
    *,
    store: SqlAlchemyPitStore,
    instruments: dict[str, tuple[str, int]],
    frequency: str,
    bar_spec: Any,
) -> type[PitDataClientFactory]:
    """动态子类绑定 PIT store 与标的映射（同 exec_factory_for 的模式）。"""
    return type(
        "PitLiveDataClientFactory",
        (PitDataClientFactory,),
        {
            "store": store,
            "instruments": instruments,
            "frequency": frequency,
            "bar_spec": bar_spec,
            "instance": None,
        },
    )
