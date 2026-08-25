# LiveFeed 回放器（回测 / Paper Trading 数据平面拆分）实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增 LiveFeed 生产者（时钟驱动的历史回放器），持续把新 bar 写进 PIT，让 Paper Trading 节点获得与真实实时行情同构的数据平面；回测链路零改动。

**Architecture:** 设计见 `docs/plans/2026-08-25-backtest-paper-livefeed-design.md`（已确认方案 C：LiveFeed 接口 + 回放器首实现）。源历史分钟线只提供价格序列；`event_time` 由虚拟行情时钟生成（paper 节点按 event_time 水位线消费，原始历史时间戳必然早于水位线，原样重放会被拦掉）。写入格式与 `scripts/ingest-market-data.py` 完全一致（`market.minute.{open,high,low,close,volume}`）。

**Tech Stack:** Python 3.12、SQLAlchemy（PIT store）、既有 `markets/nt/sessions.py` 交易时段表、Docker compose（api 镜像内跑测试）。

**关键背景（执行者须知）：**
- 测试不在宿主机跑（宿主机 Python 3.10），一律用：
  `docker compose run --rm --no-deps -v "$PWD/src:/app/src" -v "$PWD/tests:/app/tests" api pytest <path> -q`
- `RawPITRow` 字段：`source_id, dataset_id, field, instrument_id, event_time, available_time, ingested_at, revision_id, license_tag, value_type, value`（见 `src/quant_platform/data_gateway/loader.py:63`）。
- `Bar` 属性：`timestamp/open/high/low/close/volume`（见 `src/quant_platform/data_gateway/resolver.py:21`）。
- `SqlAlchemyPitStore.persist(rows)` 幂等：同 `(field, instrument, event_time, revision)` 去重（见 `src/quant_platform/data_gateway/pit_store.py:100`）。
- `load_bars_range(store=, instrument_ids=, frequency=, start=, end=)` 返回 `dict[str, list[Bar]]`（见 `src/quant_platform/paper/data_client.py`）。
- 交易时段表：`A_SHARE_SESSIONS`、`FUTURES_DAY_SESSIONS`、`FUTURES_NIGHT_SESSIONS`（见 `src/quant_platform/markets/nt/sessions.py`）。
- 测试用内存 sqlite 造 store 的模式参考 `tests/paper/test_data_client.py` 的 `make_store`。

---

### Task 1: 虚拟行情时钟（VirtualMarketClock）

**Files:**
- Create: `src/quant_platform/paper/live_feed.py`
- Test: `tests/paper/test_live_feed.py`

**Step 1: 写失败测试**

```python
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
```

**Step 2: 跑测试确认失败**

Run: `docker compose run --rm --no-deps -v "$PWD/src:/app/src" -v "$PWD/tests:/app/tests" api pytest tests/paper/test_live_feed.py -q`
Expected: FAIL（`ModuleNotFoundError: quant_platform.paper.live_feed`）

**Step 3: 实现**

创建 `src/quant_platform/paper/live_feed.py`：

```python
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
    """单根 bar → 5 条 PIT 行（与 ingest-market-data.py 的分钟线格式一致）。"""
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
            available_time=ingested,
            ingested_at=ingested,
            revision_id=revision_id,
            license_tag="exploratory",
            value_type="decimal",
            value=str(values[name]),
        )
        for name in BAR_FIELDS
    ]
```

**Step 4: 跑测试确认通过**

Run: `docker compose run --rm --no-deps -v "$PWD/src:/app/src" -v "$PWD/tests:/app/tests" api pytest tests/paper/test_live_feed.py -q`
Expected: PASS（5 项）

**Step 5: Commit**

```bash
git add src/quant_platform/paper/live_feed.py tests/paper/test_live_feed.py
git commit -m "feat(paper): LiveFeed 虚拟行情时钟与 PIT 行映射"
```

---

### Task 2: ReplayFeed 主循环

**Files:**
- Modify: `src/quant_platform/paper/live_feed.py`（追加 `ReplayFeed`）
- Test: `tests/paper/test_live_feed.py`

**Step 1: 写失败测试（内存 sqlite 端到端）**

```python
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


def test_replay_feed_writes_new_bars_on_virtual_clock() -> None:
    """回放器把源价格序列以虚拟时钟 event_time 写入 PIT，paper 水位线可见。"""
    import threading
    import time as time_mod

    from quant_platform.paper.data_client import load_bars_range
    from quant_platform.paper.live_feed import ReplayFeed

    source_start = datetime(2026, 8, 17, 9, 0, tzinfo=SH)
    store = make_store(_minute_rows("RB2610.SHF", 10, source_start))
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
            start=live_start,
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


def test_replay_feed_idle_when_source_exhausted() -> None:
    """追平源序列后不退出、不再写入（与真实行情收盘同构）。"""
    import threading
    import time as time_mod

    store = make_store(
        _minute_rows("RB2610.SHF", 2, datetime(2026, 8, 17, 9, 0, tzinfo=SH))
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

    from quant_platform.paper.data_client import load_bars_range

    loaded = load_bars_range(
        store=store,
        instrument_ids=("RB2610.SHF",),
        frequency="5m",
        start=datetime(2026, 8, 25, tzinfo=SH),
    )["RB2610.SHF"]
    assert len(loaded) == 2  # 只有 2 根，没有空转注水
    assert not thread.is_alive()
```

注：`BAR_FIELDS_FOR_TEST = ("open", "high", "low", "close", "volume")`，`make_store` 从 `tests/paper/test_data_client.py` 复制模式（minute 数据注意 `field_prefix` 用 `market.minute`）。

**Step 2: 跑测试确认失败**

Run: `docker compose run --rm --no-deps -v "$PWD/src:/app/src" -v "$PWD/tests:/app/tests" api pytest tests/paper/test_live_feed.py -q -k replay`
Expected: FAIL（`ImportError: cannot import name 'ReplayFeed'`）

**Step 3: 实现（追加到 `live_feed.py`）**

```python
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
```

**Step 4: 跑测试确认通过**

Run: `docker compose run --rm --no-deps -v "$PWD/src:/app/src" -v "$PWD/tests:/app/tests" api pytest tests/paper/test_live_feed.py -q`
Expected: PASS（7 项）

**Step 5: Commit**

```bash
git add src/quant_platform/paper/live_feed.py tests/paper/test_live_feed.py
git commit -m "feat(paper): ReplayFeed 主循环——历史价格按虚拟时钟直播进 PIT"
```

---

### Task 3: 入口脚本 + compose 服务

**Files:**
- Create: `scripts/live-feed.py`
- Modify: `compose.yaml`（在 `paper-node` 服务后追加 `live-feed` 服务）

**Step 1: 入口脚本**

创建 `scripts/live-feed.py`：

```python
"""LiveFeed 回放器：历史价格 × 虚拟行情时钟 → PIT（paper trading 数据平面）。

用法（api 容器内）：
    python scripts/live-feed.py --instruments RB2610.SHF --speed 10

paper 节点零改动：PitBarPoller 按水位线消费新 bar，与真实实时行情同构。
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from quant_platform.config import get_settings  # noqa: E402
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore  # noqa: E402
from quant_platform.paper.live_feed import ReplayFeed  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instruments", required=True, help="逗号分隔，如 RB2610.SHF,AU2610.SHF")
    parser.add_argument("--market", default="CN_COMMODITY_FUTURES")
    parser.add_argument("--speed", type=float, default=10.0, help="回放倍速（1=真实速度）")
    parser.add_argument("--source-from", default=None, help="源价格序列起点（ISO 日期）")
    parser.add_argument("--start-at", default=None, help="虚拟行情时钟起点（ISO 时间，默认当前）")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(str(settings.database_url), pool_pre_ping=True)
    feed = ReplayFeed(
        store=SqlAlchemyPitStore(sessionmaker(engine)),
        instrument_ids=tuple(args.instruments.split(",")),
        market=args.market,
        speed=args.speed,
        source_from=(
            datetime.fromisoformat(args.source_from) if args.source_from else None
        ),
        start_at=datetime.fromisoformat(args.start_at) if args.start_at else None,
    )
    stop = Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    print(f"live-feed replaying {args.instruments} at {args.speed}x", flush=True)
    feed.run(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

（顶部补 `from datetime import datetime`。）

**Step 2: compose 服务**

在 `compose.yaml` 的 `paper-node` 服务之后、`volumes:` 之前追加：

```yaml
  live-feed:
    image: quant-platform-api:local
    build:
      context: .
      args:
        UV_EXTRAS: --extra data
    environment: *app-environment
    volumes:
      - ./config:/app/config:ro
    command:
      - python
      - scripts/live-feed.py
      - --instruments
      - ${LIVE_FEED_INSTRUMENTS:-RB2610.SHF}
      - --speed
      - ${LIVE_FEED_SPEED:-10}
    depends_on:
      migrate:
        condition: service_completed_successfully
    profiles: ["paper"]
    restart: unless-stopped
```

**Step 3: 冒烟（不进 CI 的手工验证）**

```bash
docker compose build api
docker compose --profile paper up -d live-feed
sleep 30
docker exec quant-postgres-1 psql -U quant_app -d quant_platform -c \
  "select max(event_time), count(*) from pit_observations where source_id='live-feed-replay';"
# 预期：count 持续增长，max(event_time) 落在当前交易时段内
docker compose --profile paper stop live-feed
```

**Step 4: Commit**

```bash
git add scripts/live-feed.py compose.yaml
git commit -m "feat(paper): live-feed 入口脚本与 compose 服务（profile: paper）"
```

---

### Task 4: 端到端验收（回放行情驱动 paper 账户交易）

无新代码，验收步骤：

```bash
# 1. 起回放器（RB2610，10 倍速）
docker compose --profile paper up -d live-feed

# 2. 恢复并启动 RB paper 账户节点（账户当前 PAUSED 且空仓）
curl -s -X POST "http://localhost:3090/api/quant/v1/paper/accounts/pa_8f2fddcc2b3f4abd9e5a1187f63429eb:resume"
curl -s -X POST "http://localhost:3090/api/quant/v1/paper/accounts/pa_8f2fddcc2b3f4abd9e5a1187f63429eb:start-node"

# 3. 观察（每 60s 一个周期）
docker exec quant-postgres-1 psql -U quant_app -d quant_platform -c \
  "select cycles_total, bars_total from paper_run_state where account_id='pa_8f2fddcc2b3f4abd9e5a1187f63429eb';"
# 预期：bars_total 随回放增长（不再恒为 0）

# 4. UI 验证：http://localhost:3090/paper?account=pa_8f2fddcc2b3f4abd9e5a1187f63429eb
# 预期：DATA-ENGINE「已推送 K 线」增长；策略出现金叉时订单/成交 Tab 出现记录
```

验收标准：
- `bars_total` 持续增长；策略仅在新 bar 上决策（预热零订单）
- 回测链路（研究任务/对拍）行为不变：`docker compose run --rm --no-deps -v "$PWD/src:/app/src" -v "$PWD/tests:/app/tests" api pytest tests/paper/ -q` 全绿

```bash
git add -A && git commit -m "test(paper): live-feed 端到端验收记录" || true
```
