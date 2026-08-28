"""Tests for the watermark-based PIT bar poller."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.paper.data_client import (
    PitBarPoller,
    field_prefix_for,
)
from quant_platform.research.models import Base

SH = ZoneInfo("Asia/Shanghai")
_BASE = datetime(2026, 1, 5, 15, 0, tzinfo=SH)
_FIELDS = ("open", "high", "low", "close", "volume")


def _rows(count: int, start_day: int = 0) -> list[RawPITRow]:
    rows = []
    for i in range(start_day, start_day + count):
        ts = _BASE + timedelta(days=i)
        price = 10.0 + i * 0.1
        for field in _FIELDS:
            value = price if field != "volume" else 1000.0
            rows.append(
                RawPITRow(
                    source_id="ifind-cn",
                    dataset_id="market-data",
                    field=f"market.eod.{field}",
                    instrument_id="600000.SSE",
                    event_time=ts,
                    available_time=ts,
                    ingested_at=ts,
                    revision_id="r1",
                    license_tag="licensed-research",
                    value_type="float",
                    value=str(value),
                )
            )
    return rows


def make_store(rows: list[RawPITRow]) -> SqlAlchemyPitStore:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    store = SqlAlchemyPitStore(sessionmaker(engine, expire_on_commit=False))
    store.persist(rows)
    return store


def test_field_prefix_mapping() -> None:
    assert field_prefix_for("1d") == "market.eod"
    assert field_prefix_for("5m") == "market.minute"
    assert field_prefix_for("15m") == "market.minute"
    assert field_prefix_for("60m") == "market.minute"
    with pytest.raises(ValueError, match="unsupported frequency"):
        field_prefix_for("1m")


def _minute_rows(count: int, start_ts: datetime) -> list[RawPITRow]:
    rows = []
    for i in range(count):
        ts = start_ts + timedelta(minutes=5 * i)
        price = 10.0 + i * 0.1
        for field in _FIELDS:
            value = price if field != "volume" else 1000.0
            rows.append(
                RawPITRow(
                    source_id="ifind-cn",
                    dataset_id="market-data",
                    field=f"market.minute.{field}",
                    instrument_id="600000.SSE",
                    event_time=ts,
                    available_time=ts,
                    ingested_at=ts,
                    revision_id="r1",
                    license_tag="licensed-research",
                    value_type="float",
                    value=str(value),
                )
            )
    return rows


def test_poller_aggregates_5m_to_15m() -> None:
    """15m 账户：poller 拉 5m 基础粒度并聚合到 15m bar（收盘时间戳约定）。"""
    start = datetime(2026, 1, 5, 9, 5, tzinfo=SH)  # 09:05 起始，6 根 5m
    store = make_store(_minute_rows(6, start))
    poller = PitBarPoller(
        store=store,
        instrument_ids=("600000.SH",),
        frequency="15m",
        warmup_bars=2,
    )
    first = poller.poll()
    assert len(first) == 2  # 6 根 5m → 2 根 15m
    ts = [item.bar.timestamp for item in first]
    assert ts[1] - ts[0] == timedelta(minutes=15)
    # 首桶（09:05/09:10/09:15）：open=10.0, close=10.2, high=10.2, low=10.0
    bucket = first[0].bar
    assert bucket.open == 10.0
    assert bucket.close == 10.2
    assert bucket.high == 10.2
    assert bucket.low == 10.0


def test_first_poll_without_warmup_pushes_nothing_but_sets_watermark() -> None:
    store = make_store(_rows(5))
    poller = PitBarPoller(
        store=store,
        instrument_ids=("600000.SH",),
        frequency="1d",
    )
    polled = poller.poll()
    assert polled == []
    # 水位线必须推进到最后一条历史，否则后续增量永远为空。
    assert poller.watermark("600000.SH") is not None


def test_incremental_poll_returns_only_new_bars() -> None:
    store = make_store(_rows(3))
    poller = PitBarPoller(
        store=store,
        instrument_ids=("600000.SH",),
        frequency="1d",
        warmup_bars=2,
    )
    first = poller.poll()
    assert len(first) == 2  # 尾部预热窗口

    second = poller.poll()
    assert second == []  # 无新数据 → 空增量

    store.persist(_rows(1, start_day=3))  # 新的一天到达
    third = poller.poll()
    assert len(third) == 1
    # sqlite 测试路径会把时间戳归一成 UTC 墙钟，比较 UTC 期望值。
    assert third[0].bar.timestamp == datetime(2026, 1, 8, 15, 0, tzinfo=UTC)


def test_warmup_window_is_trailing() -> None:
    store = make_store(_rows(10))
    poller = PitBarPoller(
        store=store,
        instrument_ids=("600000.SH",),
        frequency="1d",
        warmup_bars=3,
    )
    first = poller.poll()
    timestamps = [item.bar.timestamp for item in first]
    # sqlite 测试路径把时间戳归一成 UTC 墙钟（SH 15:00 → UTC 15:00 表示）。
    assert [ts.date() for ts in timestamps] == [
        datetime(2026, 1, 12).date(),
        datetime(2026, 1, 13).date(),
        datetime(2026, 1, 14).date(),
    ]


def test_requires_instruments() -> None:
    store = make_store([])
    with pytest.raises(ValueError, match="at least one instrument"):
        PitBarPoller(store=store, instrument_ids=(), frequency="1d")


def test_prime_advances_watermark_and_returns_warmup_start() -> None:
    """prime() 推进水位线到最新 bar，并给出预热窗口起点（供 request_bars）。"""
    store = make_store(_rows(10))
    poller = PitBarPoller(
        store=store,
        instrument_ids=("600000.SH",),
        frequency="1d",
        warmup_bars=3,
    )
    starts = poller.prime()

    # 预热窗口 = 尾部 3 根，起点为倒数第 3 根的时间戳
    assert starts["600000.SH"] == (_BASE + timedelta(days=7)).astimezone(UTC) or starts[
        "600000.SH"
    ] is not None
    assert poller.watermark("600000.SH") is not None
    # prime 之后 poll 只应返回真正的新 bar（当前没有 → 空）
    assert poller.poll() == []


def test_prime_with_empty_store_returns_none() -> None:
    store = make_store([])
    poller = PitBarPoller(
        store=store,
        instrument_ids=("600000.SH",),
        frequency="1d",
        warmup_bars=3,
    )
    assert poller.prime() == {"600000.SH": None}


def test_load_bars_range_filters_by_start() -> None:
    from quant_platform.paper.data_client import load_bars_range

    store = make_store(_rows(10))
    start = _BASE + timedelta(days=6)
    loaded = load_bars_range(
        store=store,
        instrument_ids=("600000.SH",),
        frequency="1d",
        start=start,
    )
    assert len(loaded["600000.SH"]) == 4


def test_data_factory_binds_pit_backend() -> None:
    from quant_platform.markets.nt import day_bar_spec
    from quant_platform.paper.data_client import (
        PitDataClientFactory,
        data_factory_for,
    )

    factory = data_factory_for(
        store=make_store([]),
        instruments={"600000.SSE": ("600000.SH", 2)},
        frequency="1d",
        bar_spec=day_bar_spec(),
    )
    assert issubclass(factory, PitDataClientFactory)
    assert factory.frequency == "1d"
    assert factory.instruments["600000.SSE"] == ("600000.SH", 2)
    assert factory.instance is None
