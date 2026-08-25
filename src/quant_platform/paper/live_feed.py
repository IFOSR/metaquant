"""LiveFeed：把历史 K 线按虚拟行情时钟直播进 PIT（paper trading 的数据平面）。

回测与 paper trading 共享同一份冻结策略与撮合语义，差异只在数据平面：
回测读 PIT 封闭区间；paper 消费 LiveFeed 持续写入的新 bar。本模块是
LiveFeed 的首个实现——时钟驱动的历史回放器：源历史数据只提供价格序列，
event_time 由虚拟行情时钟生成（paper 节点按 event_time 水位线消费，
原始历史时间戳必然早于水位线，原样重放会被拦掉）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Event
from zoneinfo import ZoneInfo

from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.data_gateway.resolver import Bar
from quant_platform.markets.nt.sessions import (
    A_SHARE_SESSIONS,
    FUTURES_DAY_SESSIONS,
    FUTURES_NIGHT_SESSIONS,
    TradingSession,
)
from quant_platform.paper.data_client import load_bars_range

SHANGHAI = ZoneInfo("Asia/Shanghai")
BAR_FIELDS = ("open", "high", "low", "close", "volume")
FUTURES_SESSIONS = FUTURES_DAY_SESSIONS + FUTURES_NIGHT_SESSIONS


def sessions_for_market(market: str) -> tuple[TradingSession, ...]:
    return A_SHARE_SESSIONS if market == "CN_A" else FUTURES_SESSIONS


class VirtualMarketClock:
    """按交易时段推进的虚拟行情时钟（固定 bar 网格，跳过非交易时段与周末）。"""

    def __init__(
        self,
        *,
        start: datetime,
        step: timedelta,
        sessions: tuple[TradingSession, ...],
    ) -> None:
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("start must be timezone-aware")
        self._step = step
        self._sessions = tuple(sorted(sessions, key=lambda s: s.open))
        self._next = self._align(start.astimezone(SHANGHAI))

    def _align(self, candidate: datetime) -> datetime:
        """快进 candidate 到下一个落在交易时段内的时刻。"""
        while True:
            if candidate.weekday() < 5 and any(
                session.contains(candidate.time()) for session in self._sessions
            ):
                return candidate
            candidate = self._jump(candidate)

    def _jump(self, candidate: datetime) -> datetime:
        """跳到 candidate 之后最近的时段开盘（跨天则次日，周末顺延）。"""
        for offset in range(0, 8):
            day = (candidate + timedelta(days=offset)).date()
            if day.weekday() >= 5:
                continue
            for session in self._sessions:
                open_dt = datetime.combine(day, session.open, tzinfo=SHANGHAI)
                if open_dt > candidate:
                    return open_dt
        raise ValueError("no trading session within 8 days")

    def advance(self) -> datetime:
        """返回下一根 bar 的 event_time（UTC）并推进时钟。"""
        current = self._next
        self._next = self._align(current + self._step)
        return current.astimezone(UTC)


def bar_to_pit_rows(
    *,
    bar: Bar,
    instrument_id: str,
    event_time: datetime,
    revision_id: str,
    ingested: datetime,
) -> list[RawPITRow]:
    """单根 bar → 5 条 PIT 行（与 ingest-market-data.py 的分钟线格式一致）。

    available_time 取虚拟行情时刻（= event_time）：回放器是模拟行情的
    生产者，数据"在其（虚拟）发生时刻可见"；PIT 读取只按 event_time
    区间过滤，不做 as-of 可见性过滤，paper 节点因此即时可见。
    加速回放时虚拟时刻可能领先真实墙钟，ingested_at 随之钳到
    event_time（PIT 不变量：event_time <= available_time <= ingested_at）。
    """
    values = {
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }
    return [
        RawPITRow(
            source_id="live-feed-replay",
            dataset_id="market-minute",
            field=f"market.minute.{name}",
            instrument_id=instrument_id,
            event_time=event_time,
            available_time=event_time,
            ingested_at=max(ingested, event_time),
            revision_id=revision_id,
            license_tag="exploratory",
            value_type="decimal",
            value=str(values[name]),
        )
        for name in BAR_FIELDS
    ]


@dataclass
class ReplayFeed:
    """时钟驱动的历史回放器：源价格序列 × 虚拟行情时钟 → PIT。"""

    store: SqlAlchemyPitStore
    instrument_ids: tuple[str, ...]
    market: str
    speed: float = 10.0
    source_from: datetime | None = None
    start_at: datetime | None = None
    step: timedelta = field(default=timedelta(minutes=5))
    source_frequency: str = "5m"
    idle_heartbeat_seconds: float = 5.0

    def run(self, stop: Event) -> None:
        bars_by_inst = load_bars_range(
            store=self.store,
            instrument_ids=self.instrument_ids,
            frequency=self.source_frequency,
            start=self.source_from,
        )
        series = [bars_by_inst.get(inst, []) for inst in self.instrument_ids]
        total = min((len(s) for s in series if s), default=0)
        if total == 0:
            # 没有源数据也要常驻：真实 feed 在行情真空期同样空转。
            while not stop.wait(self.idle_heartbeat_seconds):
                pass
            return
        clock = VirtualMarketClock(
            start=self.start_at or datetime.now(UTC),
            step=self.step,
            sessions=sessions_for_market(self.market),
        )
        revision = f"replay-{datetime.now(UTC):%Y%m%dT%H%M%S}"
        wall_interval = self.step.total_seconds() / max(self.speed, 0.01)
        idx = 0
        while not stop.is_set():
            if idx >= total:
                stop.wait(self.idle_heartbeat_seconds)
                continue
            event_time = clock.advance()
            ingested = datetime.now(UTC)
            for inst, bars in zip(self.instrument_ids, series, strict=True):
                if idx < len(bars):
                    self.store.persist(
                        bar_to_pit_rows(
                            bar=bars[idx],
                            instrument_id=inst,
                            event_time=event_time,
                            revision_id=revision,
                            ingested=ingested,
                        )
                    )
            idx += 1
            stop.wait(wall_interval)
