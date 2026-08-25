"""Tests for the LiveFeed replay clock and PIT row mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from quant_platform.markets.nt.sessions import FUTURES_DAY_SESSIONS, FUTURES_NIGHT_SESSIONS
from quant_platform.paper.live_feed import VirtualMarketClock

SH = ZoneInfo("Asia/Shanghai")
SESSIONS = FUTURES_DAY_SESSIONS + FUTURES_NIGHT_SESSIONS
STEP = timedelta(minutes=5)


def clock_at(y, m, d, hh, mm):
    return VirtualMarketClock(
        start=datetime(y, m, d, hh, mm, tzinfo=SH), step=STEP, sessions=SESSIONS
    )


def test_clock_steps_within_session() -> None:
    clock = clock_at(2026, 8, 25, 9, 0)  # 周二 09:00 日盘开盘
    assert clock.advance() == datetime(2026, 8, 25, 9, 0, tzinfo=SH).astimezone(UTC)
    assert clock.advance() == datetime(2026, 8, 25, 9, 5, tzinfo=SH).astimezone(UTC)


def test_clock_skips_lunch_break() -> None:
    clock = clock_at(2026, 8, 25, 11, 25)
    clock.advance()  # 11:25
    # 11:30 不在任何时段内（11:30-13:30 休市）→ 跳到 13:30
    assert clock.advance() == datetime(2026, 8, 25, 13, 30, tzinfo=SH).astimezone(UTC)


def test_clock_skips_to_night_session() -> None:
    clock = clock_at(2026, 8, 25, 14, 55)
    clock.advance()  # 14:55
    # 15:00 收盘 → 跳到夜盘 21:00
    assert clock.advance() == datetime(2026, 8, 25, 21, 0, tzinfo=SH).astimezone(UTC)


def test_clock_skips_weekend() -> None:
    clock = clock_at(2026, 8, 21, 22, 55)  # 周五夜盘
    clock.advance()  # 22:55
    # 23:00 夜盘收盘 → 跳过周末 → 周一 09:00
    assert clock.advance() == datetime(2026, 8, 24, 9, 0, tzinfo=SH).astimezone(UTC)


def test_clock_aligns_start_outside_session() -> None:
    clock = clock_at(2026, 8, 25, 12, 0)  # 午间休市
    assert clock.advance() == datetime(2026, 8, 25, 13, 30, tzinfo=SH).astimezone(UTC)


BAR_FIELDS_FOR_TEST = ("open", "high", "low", "close", "volume")


def _minute_rows(instrument_id: str, count: int, start: datetime) -> list:
    from quant_platform.data_gateway.loader import RawPITRow

    rows = []
    for i in range(count):
        ts = start + timedelta(minutes=5 * i)
        for name in BAR_FIELDS_FOR_TEST:
            rows.append(
                RawPITRow(
                    source_id="akshare-cn",
                    dataset_id="market-minute",
                    field=f"market.minute.{name}",
                    instrument_id=instrument_id,
                    event_time=ts,
                    available_time=ts,
                    ingested_at=ts,
                    revision_id="r1",
                    license_tag="exploratory",
                    value_type="decimal",
                    value="3000.0",
                )
            )
    return rows


def make_store(rows: list):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
    from quant_platform.research.models import Base

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    store = SqlAlchemyPitStore(sessionmaker(engine, expire_on_commit=False))
    store.persist(rows)
    return store


def make_file_engine(tmp_path, rows: list):
    """文件库：回放器（写线程）与读侧各自持有连接，避免共享连接的可见性问题。"""
    from sqlalchemy import create_engine

    from quant_platform.research.models import Base

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/pit.db")
    Base.metadata.create_all(engine)
    if rows:
        from sqlalchemy.orm import sessionmaker

        from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore

        SqlAlchemyPitStore(sessionmaker(engine)).persist(rows)
    return engine


def test_replay_feed_writes_new_bars_on_virtual_clock(tmp_path) -> None:
    """回放器把源价格序列以虚拟时钟 event_time 写入 PIT，paper 水位线可见。"""
    import threading
    import time as time_mod

    from sqlalchemy.orm import sessionmaker

    from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
    from quant_platform.paper.data_client import load_bars_range
    from quant_platform.paper.live_feed import ReplayFeed

    source_start = datetime(2026, 8, 17, 9, 0, tzinfo=SH)
    engine = make_file_engine(tmp_path, _minute_rows("RB2610.SHF", 10, source_start))
    store = SqlAlchemyPitStore(sessionmaker(engine))
    live_start = datetime(2026, 8, 25, 9, 0, tzinfo=SH)
    feed = ReplayFeed(
        store=store,
        instrument_ids=("RB2610.SHF",),
        market="CN_COMMODITY_FUTURES",
        speed=1000.0,  # 测试不等待墙钟
        source_from=source_start,
        start_at=live_start,
    )
    stop = threading.Event()
    thread = threading.Thread(target=feed.run, args=(stop,), daemon=True)
    thread.start()
    deadline = time_mod.time() + 10
    loaded = []
    while time_mod.time() < deadline:
        loaded = load_bars_range(
            store=store, instrument_ids=("RB2610.SHF",), frequency="5m",
            start=live_start.astimezone(UTC),  # sqlite 存的是 UTC naive
        )["RB2610.SHF"]
        if len(loaded) >= 10:
            break
        time_mod.sleep(0.05)
    stop.set()
    thread.join(timeout=5)

    # 10 根源 bar 全部以新 event_time 写入；第一根即 live_start
    assert len(loaded) == 10
    assert loaded[0].timestamp == live_start.astimezone(UTC)
    # 源数据（旧 event_time）仍在，互不干扰
    all_bars = load_bars_range(
        store=store, instrument_ids=("RB2610.SHF",), frequency="5m"
    )["RB2610.SHF"]
    assert len(all_bars) == 20


def test_replay_feed_idle_when_source_exhausted(tmp_path) -> None:
    """追平源序列后不退出、不再写入（与真实行情收盘同构）。"""
    import threading
    import time as time_mod

    from sqlalchemy.orm import sessionmaker

    from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
    from quant_platform.paper.data_client import load_bars_range
    from quant_platform.paper.live_feed import ReplayFeed

    store = SqlAlchemyPitStore(
        sessionmaker(
            make_file_engine(
                tmp_path,
                _minute_rows("RB2610.SHF", 2, datetime(2026, 8, 17, 9, 0, tzinfo=SH)),
            )
        )
    )
    feed = ReplayFeed(
        store=store,
        instrument_ids=("RB2610.SHF",),
        market="CN_COMMODITY_FUTURES",
        speed=1000.0,
        source_from=datetime(2026, 8, 17, tzinfo=SH),
        start_at=datetime(2026, 8, 25, 9, 0, tzinfo=SH),
    )
    stop = threading.Event()
    thread = threading.Thread(target=feed.run, args=(stop,), daemon=True)
    thread.start()
    time_mod.sleep(1.5)
    stop.set()
    thread.join(timeout=5)

    loaded = load_bars_range(
        store=store,
        instrument_ids=("RB2610.SHF",),
        frequency="5m",
        start=datetime(2026, 8, 25, tzinfo=SH),
    )["RB2610.SHF"]
    assert len(loaded) == 2  # 只有 2 根，没有空转注水
    assert not thread.is_alive()
