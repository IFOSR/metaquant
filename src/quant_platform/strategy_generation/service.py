"""Backtest orchestration for generated strategies (G19-P3).

Loads bars from the PIT store for a draft's instruments, runs the generated
NautilusTrader strategy, and returns the deterministic backtest payload.

频率模型：回测频率（``1d``/``1w``/``5m``/``15m``/``30m``/``60m``）→ 基础存储
粒度（日线 / 5 分钟），读取时按需聚合（日→周、5m→15/30/60m）。多周期策略
（趋势 + 执行）按需加载两套基础数据并分别聚合。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from quant_platform.backtest.service import _build_bars
from quant_platform.data_gateway.pit_store import (
    CoverageEntry,
    SqlAlchemyPitStore,
)
from quant_platform.data_gateway.resolver import Bar
from quant_platform.markets.nt.venue import VenueSpec
from quant_platform.strategy_generation.backtest import (
    aggregate_bars,
    db_instrument_id,
    run_strategy_backtest,
)

_DEFAULT_INITIAL_CASH = Decimal("1000000")
# 窗口终点允许超出最新一根 bar 的自然日宽限：容忍周末/短假期（最后一个
# 交易日之后本来就不会有新 bar，不能因此判数据缺失）。
_TAIL_GRACE = timedelta(days=7)
# 趋势周期（更大时间粒度）加载时往前多带的历史 lead：仅供指标预热/上下文，
# 不参与被测窗口。见 ``run`` 里的说明。取值需覆盖常见日线趋势指标的回看
# （SMA(20)/MACD(26)+EMA(9) 约 35 个交易日），留足周末/节假日余量。
_TREND_WARMUP_LEAD = timedelta(days=120)


@dataclass(frozen=True, slots=True)
class _CoverageSpan:
    """同一标的 × 字段前缀跨数据源合并后的覆盖区间。"""

    row_count: int
    first_event: str
    last_event: str


def _merge_entries(
    entries: list[CoverageEntry],
) -> _CoverageSpan:
    return _CoverageSpan(
        row_count=sum(entry.row_count for entry in entries),
        first_event=min(entry.first_event for entry in entries),
        last_event=max(entry.last_event for entry in entries),
    )


def _span_payload(span: _CoverageSpan | None) -> dict[str, object] | None:
    if span is None or span.row_count == 0:
        return None
    return {
        "rows": span.row_count,
        "first_event": span.first_event,
        "last_event": span.last_event,
    }


def _base_prefix(frequency: str) -> str:
    """回测频率 → PIT 存储字段前缀（``1d``/``1w`` 用日线，分钟级用 5m）。"""
    if frequency in ("1d", "1w"):
        return "market.eod"
    return "market.minute"


class StrategyBacktestService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._store = SqlAlchemyPitStore(sessions)

    def _coverage_merged(
        self, db_ids: tuple[str, ...]
    ) -> dict[tuple[str, str], _CoverageSpan]:
        """跨数据源/revision 合并覆盖区间，避免碎片覆盖被单一最大段误报。"""
        grouped: dict[tuple[str, str], list[CoverageEntry]] = {}
        for entry in self._store.coverage(instrument_ids=db_ids):
            grouped.setdefault((entry.instrument_id, entry.field_prefix), []).append(
                entry
            )
        return {key: _merge_entries(entries) for key, entries in grouped.items()}

    def data_status(
        self,
        *,
        instrument_ids: tuple[str, ...],
        frequencies: tuple[str, ...],
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        """检查草稿标的在每个所需频率下的数据覆盖（供回测前展示与门控）。

        给定窗口时按「包含」判定，头尾各留 7 天自然日宽限（行情起点/预热、
        周末/短假）：起点超出宽限仍早于首根 bar、或终点超出宽限仍晚于末根
        bar，才判不可用。小幅缺口不算缺数据，也不回测按钮锁死。
        """
        db_ids = tuple(db_instrument_id(item) for item in instrument_ids)
        merged = self._coverage_merged(db_ids)
        items: list[dict[str, object]] = []
        all_ready = True
        for instrument_id in db_ids:
            checks: list[dict[str, object]] = []
            for frequency in frequencies:
                span = merged.get((instrument_id, _base_prefix(frequency)))
                available = span is not None and span.row_count > 0
                if available and (start is not None or end is not None):
                    assert span is not None
                    first = date.fromisoformat(span.first_event[:10])
                    last = date.fromisoformat(span.last_event[:10])
                    # 头尾都留自然日宽限：策略起点常比首根 bar 早（预热/行情起点），
                    # 终点常比末根 bar 晚（周末/短假），小幅缺口不算缺数据。
                    if start is not None and first > start + _TAIL_GRACE:
                        available = False
                    if end is not None and last < end - _TAIL_GRACE:
                        available = False
                all_ready = all_ready and available
                checks.append(
                    {
                        "frequency": frequency,
                        "available": available,
                        "required": _span_payload(span),
                    }
                )
            items.append(
                {
                    "instrument_id": instrument_id,
                    "available": all(check["available"] for check in checks),
                    "daily": _span_payload(merged.get((instrument_id, "market.eod"))),
                    "minute": _span_payload(
                        merged.get((instrument_id, "market.minute"))
                    ),
                    "checks": checks,
                }
            )
        return {
            "instrument_ids": list(db_ids),
            "frequencies": list(frequencies),
            "ready": all_ready,
            "items": items,
        }

    def _load_base_bars(
        self,
        db_ids: tuple[str, ...],
        prefix: str,
        start_dt: datetime | None,
        end_dt: datetime | None,
    ) -> dict[str, tuple[Bar, ...]]:
        rows = self._store.load(
            instrument_ids=db_ids,
            field_prefix=prefix,
            start=start_dt,
            end=end_dt,
        )
        if not rows:
            raise ValueError("MARKET_DATA_NOT_INGESTED")
        return _build_bars(rows, db_ids, prefix)

    def load_code_test_bars(
        self,
        *,
        instrument_ids: tuple[str, ...],
        frequency: str,
        trend_frequency: str | None = None,
        max_bars: int = 60,
    ) -> tuple[
        tuple[str, ...],
        dict[str, tuple[Bar, ...]],
        dict[str, tuple[Bar, ...]] | None,
    ]:
        """加载「代码正确性测试」用的基础行情切片（每标的至多 ``max_bars`` 根）。

        数据未入库时抛 ``ValueError("MARKET_DATA_NOT_INGESTED")``，由调用方转成
        「数据未就绪」的友好提示（引导用户先做数据准备）。
        """
        db_ids = tuple(db_instrument_id(item) for item in instrument_ids)
        exec_base = self._load_base_bars(db_ids, _base_prefix(frequency), None, None)
        exec_bars = {
            db_id: aggregate_bars(exec_base[db_id], frequency)[:max_bars]
            for db_id in db_ids
        }
        trend_bars: dict[str, tuple[Bar, ...]] | None = None
        if trend_frequency is not None:
            trend_base = self._load_base_bars(
                db_ids, _base_prefix(trend_frequency), None, None
            )
            trend_bars = {
                db_id: aggregate_bars(trend_base[db_id], trend_frequency)[:max_bars]
                for db_id in db_ids
            }
        return db_ids, exec_bars, trend_bars

    def run(
        self,
        *,
        code: str,
        market: str,
        instrument_ids: tuple[str, ...],
        frequency: str,
        trend_frequency: str | None = None,
        start: date | None,
        end: date | None,
        initial_cash: Decimal = _DEFAULT_INITIAL_CASH,
        venue_spec: VenueSpec | None = None,
    ) -> dict[str, object]:
        db_ids = tuple(db_instrument_id(item) for item in instrument_ids)
        start_dt = (
            datetime.combine(start, datetime.min.time(), tzinfo=UTC) if start else None
        )
        end_dt = datetime.combine(end, datetime.max.time(), tzinfo=UTC) if end else None

        # 执行周期决定被测窗口：其 base 序列只取窗口内的 bar，用于交易与盈亏。
        exec_prefix = _base_prefix(frequency)
        exec_base = self._load_base_bars(db_ids, exec_prefix, start_dt, end_dt)
        exec_bars = {
            instrument_id: aggregate_bars(exec_base[instrument_id], frequency)
            for instrument_id in db_ids
        }

        # 趋势周期只负责趋势过滤与指标预热：加载时必须带上窗口前的一段历史
        # lead，否则趋势指标（如日线 SMA/MACD）在窗口内从零冷启动——既吃掉
        # 窗口长度做无意义的预热，又因缺少窗口前上下文而产生偏差值。这种偏差
        # 实际表现为「整个回测窗口无信号、0 成交」（行情已就绪却毫无效果）。
        # lead 只喂指标，不参与被测窗口（被测窗口仍由 exec 序列决定）。
        trend_bars: dict[str, tuple[Bar, ...]] | None = None
        if trend_frequency is not None:
            trend_start_dt = (
                start_dt - _TREND_WARMUP_LEAD if start_dt is not None else None
            )
            trend_base = self._load_base_bars(
                db_ids, _base_prefix(trend_frequency), trend_start_dt, end_dt
            )
            trend_bars = {
                instrument_id: aggregate_bars(
                    trend_base[instrument_id], trend_frequency
                )
                for instrument_id in db_ids
            }
        result = run_strategy_backtest(
            code=code,
            market=market,
            instrument_ids=db_ids,
            bars_by_instrument=exec_bars,
            frequency=frequency,
            trend_bars_by_instrument=trend_bars,
            trend_frequency=trend_frequency,
            initial_cash=initial_cash,
            venue_spec=venue_spec,
        )
        return result.payload()
