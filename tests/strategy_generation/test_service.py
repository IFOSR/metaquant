"""Tests for strategy data status / backtest service orchestration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.research.models import Base
from quant_platform.strategy_generation.service import StrategyBacktestService

BASE_TS = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)

EOD_FIELDS = ("open", "high", "low", "close", "volume")


def _row(
    field: str,
    day: int,
    instrument: str = "600000.SSE",
    source_id: str = "ifind-cn",
    revision_id: str = "r1",
) -> RawPITRow:
    timestamp = BASE_TS + timedelta(days=day)
    return RawPITRow(
        source_id=source_id,
        dataset_id="market-eod",
        field=field,
        instrument_id=instrument,
        event_time=timestamp,
        available_time=timestamp,
        ingested_at=timestamp,
        revision_id=revision_id,
        license_tag="formal",
        value_type="decimal",
        value="10.0",
    )


def make_service(*, with_daily: bool = True) -> StrategyBacktestService:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    if with_daily:
        store = SqlAlchemyPitStore(sessions)
        store.persist(
            [
                _row(f"market.eod.{field}", day)
                for field in EOD_FIELDS
                for day in range(30)
            ]
        )
    return StrategyBacktestService(sessions)


def _service_with(rows: list[RawPITRow]) -> StrategyBacktestService:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    SqlAlchemyPitStore(sessions).persist(rows)
    return StrategyBacktestService(sessions)


def test_data_status_ready_when_daily_ingested() -> None:
    service = make_service(with_daily=True)
    status = service.data_status(instrument_ids=("600000.SH",), frequencies=("1d",))
    assert status["ready"] is True
    item = status["items"][0]
    assert item["instrument_id"] == "600000.SSE"  # 归一化到库内 ID
    assert item["available"] is True
    check = item["checks"][0]
    assert check["frequency"] == "1d"
    assert check["available"] is True
    assert check["required"]["rows"] == 150
    assert item["minute"] is None


def test_data_status_missing_minute_data() -> None:
    service = make_service(with_daily=True)
    status = service.data_status(instrument_ids=("600000.SH",), frequencies=("5m",))
    assert status["ready"] is False
    item = status["items"][0]
    assert item["available"] is False
    check = item["checks"][0]
    assert check["frequency"] == "5m"
    assert check["available"] is False
    assert check["required"] is None
    assert item["daily"]["rows"] == 150  # 日线可用，供前端提示切换


def test_data_status_unknown_instrument() -> None:
    service = make_service(with_daily=True)
    status = service.data_status(instrument_ids=("999999.SH",), frequencies=("1d",))
    assert status["ready"] is False
    item = status["items"][0]
    assert item["daily"] is None
    assert item["minute"] is None


def test_data_status_multi_frequency_checks_both() -> None:
    service = make_service(with_daily=True)
    status = service.data_status(
        instrument_ids=("600000.SH",), frequencies=("1d", "5m")
    )
    item = status["items"][0]
    checks = {check["frequency"]: check["available"] for check in item["checks"]}
    assert checks == {"1d": True, "5m": False}
    assert status["ready"] is False


def test_db_instrument_id_normalization() -> None:
    from quant_platform.strategy_generation.backtest import db_instrument_id

    assert db_instrument_id("600000.SH") == "600000.SSE"
    assert db_instrument_id("000001.SZ") == "000001.SZSE"
    # 期货沿用库内短后缀，不改写为 venue 名
    assert db_instrument_id("AU2610.SHF") == "AU2610.SHF"
    assert db_instrument_id("A2611.DCE") == "A2611.DCE"


def test_data_status_merges_fragmented_sources() -> None:
    """两个数据源各覆盖一段时，状态必须报合并区间，而不是只看行数最多的段。"""
    rows = [
        _row(f"market.eod.{field}", day, source_id="ifind-cn", revision_id="r1")
        for field in EOD_FIELDS
        for day in range(10)
    ] + [
        _row(
            f"market.eod.{field}",
            day,
            source_id="akshare-cn",
            revision_id="r2",
        )
        for field in EOD_FIELDS
        for day in range(20, 30)
    ]
    service = _service_with(rows)
    status = service.data_status(instrument_ids=("600000.SH",), frequencies=("1d",))
    item = status["items"][0]
    check = item["checks"][0]
    # 合并后：行数相加、首尾取并集（此前只取最大段会漏掉 akshare 的尾部）
    assert check["required"]["rows"] == 100
    assert check["required"]["first_event"].startswith("2026-08-01")
    assert check["required"]["last_event"].startswith("2026-08-30")


def test_data_status_window_beyond_coverage_not_ready() -> None:
    """请求窗口超出最新 bar 且超过宽限期 → 不可用（部分重叠不再算就绪）。"""
    service = make_service(with_daily=True)  # 覆盖 day 0..29
    d0 = BASE_TS.date()
    last = d0 + timedelta(days=29)
    ready = service.data_status(
        instrument_ids=("600000.SH",),
        frequencies=("1d",),
        start=d0,
        end=last + timedelta(days=3),
    )
    assert ready["ready"] is True  # 3 天在自然日宽限内（周末/短假期）
    beyond = service.data_status(
        instrument_ids=("600000.SH",),
        frequencies=("1d",),
        start=d0,
        end=last + timedelta(days=10),
    )
    assert beyond["ready"] is False
    check = beyond["items"][0]["checks"][0]
    assert check["available"] is False


def test_data_status_window_head_within_grace_ready() -> None:
    """窗口起点略早于最早 bar（在宽限内）→ 可用，不算缺数据。"""
    service = make_service(with_daily=True)  # 覆盖 day 0..29
    d0 = BASE_TS.date()
    status = service.data_status(
        instrument_ids=("600000.SH",),
        frequencies=("1d",),
        start=d0 - timedelta(days=3),
        end=d0 + timedelta(days=29),
    )
    assert status["ready"] is True  # 头 3 天在宽限内（行情起点/预热）


def test_data_status_window_head_beyond_grace_not_ready() -> None:
    """窗口起点超过宽限期仍早于最早 bar → 不可用。"""
    service = make_service(with_daily=True)
    d0 = BASE_TS.date()
    status = service.data_status(
        instrument_ids=("600000.SH",),
        frequencies=("1d",),
        start=d0 - timedelta(days=15),
        end=d0 + timedelta(days=29),
    )
    assert status["ready"] is False


# ── 趋势周期预热 lead（不同周期多策略回测窗口）─────────────────────────────

_TREND_GATE = """\
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators import SimpleMovingAverage
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy

class Config(StrategyConfig):
    pass


class TrendGate(Strategy):
    def __init__(self, instrument_id: str, bar_type_str: str,
                 trend_bar_type_str: str | None = None):
        super().__init__(Config(strategy_id="TG"))
        self._instrument_id = InstrumentId.from_str(instrument_id)
        self._bar_type = BarType.from_str(bar_type_str)
        self._trend_bar_type = (
            BarType.from_str(trend_bar_type_str)
            if trend_bar_type_str
            else self._bar_type
        )
        self.trend = SimpleMovingAverage(20)
        self.fast = SimpleMovingAverage(5)

    def on_start(self):
        self.register_indicator_for_bars(self._trend_bar_type, self.trend)
        self.register_indicator_for_bars(self._bar_type, self.fast)
        self.subscribe_bars(self._bar_type)
        self.subscribe_bars(self._trend_bar_type)

    def on_bar(self, bar):
        if not self.indicators_initialized():
            return
        if self.portfolio.is_flat(self._instrument_id):
            price = bar.close.as_double()
            if price > self.trend.value:
                instrument = self.cache.instrument(self._instrument_id)
                order = self.order_factory.market(
                    instrument_id=self._instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=instrument.make_qty(1),
                )
                self.submit_order(order)
"""


def _daily_pit_row(day: int, price: float) -> RawPITRow:
    timestamp = BASE_TS + timedelta(days=day)
    return RawPITRow(
        source_id="ifind-cn",
        dataset_id="market-eod",
        field="market.eod.close",
        instrument_id="RB2610.SHF",
        event_time=timestamp,
        available_time=timestamp,
        ingested_at=timestamp,
        revision_id="r1",
        license_tag="formal",
        value_type="decimal",
        value=str(price),
    )


def _minute_pit_row(day: int, index: int, price: float) -> RawPITRow:
    # 每交易日 4 根 5m bar（09:05 ~ 09:20）
    timestamp = (
        BASE_TS
        + timedelta(days=day)
        - timedelta(hours=1)
        + timedelta(minutes=5 * index)
    )
    return RawPITRow(
        source_id="ifind-cn",
        dataset_id="market-minute",
        field="market.minute.close",
        instrument_id="RB2610.SHF",
        event_time=timestamp,
        available_time=timestamp,
        ingested_at=timestamp,
        revision_id="r1",
        license_tag="formal",
        value_type="decimal",
        value=str(price),
    )


def test_run_warmed_trend_series_trades_inside_window() -> None:
    """日线趋势 + 5m 执行：趋势指标必须带窗口前历史，否则窗口内无信号。

    日线覆盖 day 0..39（SMA(20) 在 day20 前即初始化）；回测窗口限定为
    day30..39（< 20 根日线）。若趋势序列被裁剪到窗口内，SMA(20) 永远无法
    在窗口内初始化 → 0 成交；带上窗口前预热 lead 后窗口内应能开仓。
    """
    rows: list[RawPITRow] = []
    for day in range(40):
        rows.append(_daily_pit_row(day, 100.0 + day))
    for day in range(30, 40):
        for index in range(4):
            rows.append(_minute_pit_row(day, index, 100.0 + day + index * 0.1))
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    SqlAlchemyPitStore(sessions).persist(rows)
    service = StrategyBacktestService(sessions)

    window_start = (BASE_TS + timedelta(days=30)).date()
    window_end = (BASE_TS + timedelta(days=39)).date()
    payload = service.run(
        code=_TREND_GATE,
        market="CN_COMMODITY_FUTURES",
        instrument_ids=("RB2610.SHF",),
        frequency="5m",
        trend_frequency="1d",
        start=window_start,
        end=window_end,
    )
    assert payload["error"] is None
    # 趋势指标预热 lead 使窗口内可开仓（此前裁剪趋势序列会导致 0 成交）
    assert payload["metrics"]["trade_count"] > 0
    assert payload["equity_curve"]
    assert payload["start"] == window_start.isoformat()
    assert payload["end"] == window_end.isoformat()
