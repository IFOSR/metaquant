"""单因子期货日频回测服务（策略台面 V1）。

输入：已晋级因子的 ``FactorObservation`` 序列（因子值）与正式快照的
``PITRow`` 行情行（market.eod.open/high/low/close/volume）。
输出：确定性 ``BacktestResult``（净值曲线 + 指标 + ``backtest_hash``）。

本版边界（与 UI 披露一致）：
- 期货日频、毛回测（不扣手续费/滑点）
- 仓位桥规则：T 日因子值 > 0 → T+1 日起持有 +lot_size 手，< 0 → -lot_size 手，
  否则平仓。严格使用早于当根 bar 的最近因子值（对齐 decision_clock
  T_CLOSE+30m / T+1_OPEN 的日频近似，避免前视）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar as NautilusBar

from quant_platform.data_gateway.models import PITRow
from quant_platform.data_gateway.resolver import Bar
from quant_platform.experiments import FactorObservation
from quant_platform.markets.nt import (
    TargetPositionStrategy,
    backtest_hash,
    build_futures_engine,
    day_bar_spec,
    futures_contract,
    minute_bar_spec,
    run_engine,
    to_nautilus_bars,
)

_DEFAULT_INITIAL_CASH = Decimal("100000000")
_BAR_FIELDS = ("open", "high", "low", "close", "volume")

# 品种规则表：品种简称 → (price_increment, multiplier, price_precision)。
# 仅覆盖演示品种；未识别品种回退到 RB 规格。
_CONTRACT_SPECS: dict[str, tuple[str, str, int]] = {
    "RB": ("1", "10", 0),
    "AU": ("0.02", "1000", 2),
}
_VENUE_BY_SUFFIX = {
    "SHF": "SHFE",
    "INE": "INE",
    "DCE": "DCE",
    "CZC": "CZCE",
    "GFE": "GFEX",
}


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    total_return: float
    sharpe: float | None
    max_drawdown: float
    trade_count: int

    def payload(self) -> dict[str, object]:
        return {
            "total_return": self.total_return,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "trade_count": self.trade_count,
        }


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    """一笔成交（来自 NautilusTrader 成交回报）。"""

    time: str
    instrument_id: str
    side: str
    quantity: float
    price: float

    def payload(self) -> dict[str, object]:
        return {
            "time": self.time,
            "instrument_id": self.instrument_id,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
        }


@dataclass(frozen=True, slots=True)
class BacktestPosition:
    """一段持仓回合（来自 NautilusTrader 持仓回报，含已实现盈亏）。"""

    instrument_id: str
    entry: str
    peak_qty: float
    avg_px_open: float
    avg_px_close: float | None
    realized_pnl: float
    opened_at: str
    closed_at: str | None

    def payload(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "entry": self.entry,
            "peak_qty": self.peak_qty,
            "avg_px_open": self.avg_px_open,
            "avg_px_close": self.avg_px_close,
            "realized_pnl": self.realized_pnl,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
        }


@dataclass(frozen=True, slots=True)
class BacktestResult:
    factor_ir_hash: str
    instrument_ids: tuple[str, ...]
    start: str
    end: str
    frequency: str
    initial_cash: float
    lot_size: int
    metrics: BacktestMetrics
    equity_curve: tuple[tuple[str, float], ...]
    trades: tuple[BacktestTrade, ...]
    positions: tuple[BacktestPosition, ...]
    backtest_hash: str

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "factor-backtest/v2",
            "factor_ir_hash": self.factor_ir_hash,
            "instrument_ids": list(self.instrument_ids),
            "start": self.start,
            "end": self.end,
            "frequency": self.frequency,
            "initial_cash": self.initial_cash,
            "lot_size": self.lot_size,
            "gross_of_fees": True,
            "metrics": self.metrics.payload(),
            "equity_curve": [
                {"date": day, "equity": equity} for day, equity in self.equity_curve
            ],
            "trades": [trade.payload() for trade in self.trades],
            "positions": [position.payload() for position in self.positions],
            "backtest_hash": self.backtest_hash,
        }


def _split_instrument(instrument_id: str) -> tuple[str, str]:
    """``RB2610.SHF`` → (``RB2610``, ``SHFE``)。"""
    symbol, _, suffix = instrument_id.partition(".")
    venue = _VENUE_BY_SUFFIX.get(suffix.upper())
    if not symbol or venue is None:
        raise ValueError(f"unsupported instrument_id: {instrument_id}")
    return symbol, venue


def _underlying(symbol: str) -> str:
    return "".join(ch for ch in symbol if ch.isalpha()).upper()


def _build_bars(
    rows: tuple[PITRow, ...],
    instrument_ids: tuple[str, ...],
    field_prefix: str = "market.eod",
) -> dict[str, tuple[Bar, ...]]:
    """把 PIT 行聚成每个标的的 Bar 序列（按时间升序）。"""
    wanted = set(instrument_ids)
    grouped: dict[tuple[str, datetime], dict[str, float]] = {}
    for row in rows:
        if row.instrument_id not in wanted or row.value is None:
            continue
        field = row.field.removeprefix(f"{field_prefix}.")
        if field not in _BAR_FIELDS:
            continue
        grouped.setdefault((row.instrument_id, row.event_time), {})[field] = float(
            str(row.value)
        )
    per_instrument: dict[str, list[Bar]] = {item: [] for item in instrument_ids}
    for (instrument_id, event_time), fields in grouped.items():
        if "close" not in fields:
            continue
        per_instrument[instrument_id].append(
            Bar(
                timestamp=event_time,
                open=fields.get("open", fields["close"]),
                high=fields.get("high", fields["close"]),
                low=fields.get("low", fields["close"]),
                close=fields["close"],
                volume=fields.get("volume", 0.0),
            )
        )
    return {
        instrument: tuple(sorted(bars, key=lambda bar: bar.timestamp))
        for instrument, bars in per_instrument.items()
        if bars
    }


def _targets_by_bar(
    values: tuple[tuple[date, float], ...],
    bar_times: tuple[datetime, ...],
    lot_size: int,
) -> dict[datetime, int]:
    """每根 bar 的目标持仓：取严格早于 bar 日的最近因子值映射方向。

    分钟级 bar 同理：同一交易日的所有 bar 共用前一交易日信号（T 日信号，
    T+1 日起持仓），目标只在日界变化，所以实际成交发生在当日首根 bar。
    """
    ordered = tuple(sorted(values))
    targets: dict[datetime, int] = {}
    for bar_time in sorted(bar_times):
        bar_day = bar_time.date()
        value: float | None = None
        for day, candidate in ordered:
            if day >= bar_day:
                break
            value = candidate
        if value is None or value == 0.0:
            targets[bar_time] = 0
        else:
            targets[bar_time] = lot_size if value > 0 else -lot_size
    return targets


def _equity_curve(
    *,
    bars_by_instrument: dict[str, tuple[Bar, ...]],
    targets: dict[str, dict[datetime, int]],
    initial_cash: Decimal,
    trade_count: int,
    aggregate_daily: bool,
) -> tuple[tuple[tuple[str, float], ...], BacktestMetrics]:
    """盯市净值：PnL(t) = Σ pos(t-1) × (close(t) − close(t-1)) × 乘数。

    当根 bar 收盘成交，故目标仓位在计提当根 PnL 之后才生效。
    ``aggregate_daily`` 时净值曲线与指标按日聚合（分钟频回测用）。
    """
    multipliers = {
        instrument: int(
            _CONTRACT_SPECS.get(
                _underlying(_split_instrument(instrument)[0]),
                _CONTRACT_SPECS["RB"],
            )[1]
        )
        for instrument in bars_by_instrument
    }
    closes: dict[str, dict[datetime, float]] = {
        instrument: {bar.timestamp: bar.close for bar in bars}
        for instrument, bars in bars_by_instrument.items()
    }
    all_times = sorted({ts for series in closes.values() for ts in series})
    if not all_times:
        return (), BacktestMetrics(0.0, None, 0.0, trade_count)

    equity = float(initial_cash)
    points: list[tuple[datetime, float]] = []
    peak = equity
    max_drawdown = 0.0
    last_close: dict[str, float] = {}
    current_pos: dict[str, int] = {}
    for ts in all_times:
        pnl = 0.0
        for instrument, series in closes.items():
            close = series.get(ts, last_close.get(instrument))
            previous = last_close.get(instrument)
            if close is not None and previous is not None:
                pnl += (
                    current_pos.get(instrument, 0)
                    * (close - previous)
                    * multipliers[instrument]
                )
            if close is not None:
                last_close[instrument] = close
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
        points.append((ts, equity))
        for instrument, by_bar in targets.items():
            if ts in by_bar:
                current_pos[instrument] = by_bar[ts]

    if aggregate_daily:
        daily: dict[date, float] = {}
        for ts, value in points:
            daily[ts.date()] = value
        points = [
            (datetime.combine(day, time.max, tzinfo=UTC), v)
            for day, v in sorted(daily.items())
        ]

    curve: list[tuple[str, float]] = []
    returns: list[float] = []
    previous_equity = float(initial_cash)
    for ts, value in points:
        if previous_equity > 0:
            returns.append(value / previous_equity - 1.0)
        previous_equity = value
        curve.append((ts.date().isoformat(), value))

    total_return = equity / float(initial_cash) - 1.0
    sharpe: float | None = None
    if len(returns) >= 2:
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        if variance > 0:
            sharpe = mean / math.sqrt(variance) * math.sqrt(252)
    metrics = BacktestMetrics(total_return, sharpe, max_drawdown, trade_count)
    return tuple(curve), metrics


def _ns_to_iso(value: object) -> str:
    """报表时间列兼容纳秒整数与 pandas Timestamp；0/NA/NaT → 空串。"""
    if value is None or bool(pd.isna(value)):
        return ""
    if isinstance(value, pd.Timestamp):
        return datetime.fromtimestamp(value.timestamp(), tz=UTC).isoformat()
    try:
        ns = int(str(value))
    except ValueError:
        return ""
    if ns <= 0:
        return ""
    return datetime.fromtimestamp(ns / 1e9, tz=UTC).isoformat()


def _money_to_float(value: object) -> float:
    """NautilusTrader 报表里的 Money 形如 ``"100.00 CNY"``。"""
    text = str(value)
    amount, _, _ = text.partition(" ")
    return float(amount.replace(",", "").replace("_", ""))


def _extract_trades(engine: Any) -> tuple[BacktestTrade, ...]:
    fills = engine.trader.generate_order_fills_report()
    return tuple(
        BacktestTrade(
            time=_ns_to_iso(row["ts_last"]),
            instrument_id=str(row["instrument_id"]),
            side=str(row["side"]),
            quantity=float(row["filled_qty"]),
            price=float(row["avg_px"]),
        )
        for _, row in fills.iterrows()
    )


def _extract_positions(engine: Any) -> tuple[BacktestPosition, ...]:
    report = engine.trader.generate_positions_report()
    positions: list[BacktestPosition] = []
    for _, row in report.iterrows():
        ts_closed = _ns_to_iso(row["ts_closed"])
        avg_px_close = row["avg_px_close"]
        has_close = avg_px_close is not None and not bool(pd.isna(avg_px_close))
        positions.append(
            BacktestPosition(
                instrument_id=str(row["instrument_id"]),
                entry=str(row["entry"]),
                peak_qty=float(row["peak_qty"]),
                avg_px_open=float(row["avg_px_open"]),
                avg_px_close=(
                    float(avg_px_close)
                    if has_close and float(avg_px_close) > 0
                    else None
                ),
                realized_pnl=_money_to_float(row["realized_pnl"]),
                opened_at=str(row["ts_opened"]),
                closed_at=ts_closed or None,
            )
        )
    return tuple(positions)


def run_factor_backtest(
    *,
    factor_ir_hash: str,
    observations: tuple[FactorObservation, ...],
    snapshot_rows: tuple[PITRow, ...],
    instrument_ids: tuple[str, ...] | None = None,
    start: date | None = None,
    end: date | None = None,
    frequency: str = "1d",
    initial_cash: Decimal = _DEFAULT_INITIAL_CASH,
    lot_size: int = 1,
) -> BacktestResult:
    """对已晋级因子的观测值跑 NautilusTrader 方向性回测。

    ``start``/``end`` 限定回测窗口（按 bar 日过滤行情）；因子值不截断，
    窗口首日的仓位仍由窗口之前的最近因子信号决定。
    ``frequency``：``1d``（日频）或 ``5m``（5 分钟；净值按日聚合展示）。
    """
    if lot_size < 1:
        raise ValueError("lot_size must be positive")
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if start is not None and end is not None and end < start:
        raise ValueError("end must not precede start")
    if frequency not in ("1d", "5m"):
        raise ValueError("frequency must be 1d or 5m")
    field_prefix = "market.eod" if frequency == "1d" else "market.minute"
    bar_spec = day_bar_spec() if frequency == "1d" else minute_bar_spec(5)
    bar_type_suffix = (
        "1-DAY-LAST-EXTERNAL" if frequency == "1d" else "5-MINUTE-LAST-EXTERNAL"
    )

    if instrument_ids is None:
        instrument_ids = tuple(
            sorted(
                {item.instrument_id for item in observations if item.value is not None}
            )
        )
    if not instrument_ids:
        raise ValueError("no instruments available for backtest")

    if start is not None or end is not None:
        snapshot_rows = tuple(
            row
            for row in snapshot_rows
            if (start is None or row.event_time.date() >= start)
            and (end is None or row.event_time.date() <= end)
        )

    bars_by_instrument = _build_bars(snapshot_rows, instrument_ids, field_prefix)
    missing = [item for item in instrument_ids if item not in bars_by_instrument]
    if missing:
        raise ValueError(f"no market data for instruments: {', '.join(missing)}")

    factor_by_instrument: dict[str, list[tuple[date, float]]] = {
        item: [] for item in instrument_ids
    }
    for item in observations:
        if item.instrument_id in factor_by_instrument and item.value is not None:
            factor_by_instrument[item.instrument_id].append(
                (item.event_time.date(), item.value)
            )

    venues = {_split_instrument(item)[1] for item in instrument_ids}
    if len(venues) != 1:
        raise ValueError("all instruments must share one venue")
    venue = venues.pop()

    contracts = {}
    all_nt_bars: list[NautilusBar] = []
    engine = None
    for instrument_id in instrument_ids:
        symbol, instrument_venue = _split_instrument(instrument_id)
        underlying = _underlying(symbol)
        increment, multiplier, precision = _CONTRACT_SPECS.get(
            underlying, _CONTRACT_SPECS["RB"]
        )
        days = [bar.timestamp for bar in bars_by_instrument[instrument_id]]
        contract = futures_contract(
            symbol=symbol,
            venue=instrument_venue,
            underlying=underlying,
            price_increment=increment,
            multiplier=multiplier,
            price_precision=precision,
            activation_ns=int((min(days) - timedelta(days=30)).timestamp() * 1e9),
            expiration_ns=int((max(days) + timedelta(days=120)).timestamp() * 1e9),
        )
        contracts[instrument_id] = (contract, precision)
        if engine is None:
            engine = build_futures_engine(
                instrument=contract, initial_cash=initial_cash, venue=venue
            )
        else:
            engine.add_instrument(contract)
        all_nt_bars.extend(
            to_nautilus_bars(
                bars_by_instrument[instrument_id],
                instrument_id=contract.id,
                bar_spec=bar_spec,
                price_precision=precision,
            )
        )
    assert engine is not None  # instrument_ids 非空

    targets: dict[str, dict[datetime, int]] = {}
    for instrument_id in instrument_ids:
        contract, _ = contracts[instrument_id]
        bar_times = tuple(bar.timestamp for bar in bars_by_instrument[instrument_id])
        by_bar = _targets_by_bar(
            tuple(factor_by_instrument[instrument_id]), bar_times, lot_size
        )
        targets[instrument_id] = by_bar

        def target_fn(bar: Any, targets: dict[datetime, int] = by_bar) -> int:
            return targets.get(datetime.fromtimestamp(bar.ts_event / 1e9, tz=UTC), 0)

        engine.add_strategy(
            TargetPositionStrategy(
                StrategyConfig(strategy_id=f"bt-{contract.id.symbol}"),
                instrument_id=str(contract.id),
                target_qty_fn=target_fn,
                bar_type_str=f"{contract.id}-{bar_type_suffix}",
            )
        )

    run_engine(engine, bars=all_nt_bars)

    fills = engine.trader.generate_order_fills_report()
    curve, metrics = _equity_curve(
        bars_by_instrument=bars_by_instrument,
        targets=targets,
        initial_cash=initial_cash,
        trade_count=len(fills),
        aggregate_daily=frequency != "1d",
    )
    all_bar_days = sorted(
        {bar.timestamp.date() for bars in bars_by_instrument.values() for bar in bars}
    )
    return BacktestResult(
        factor_ir_hash=factor_ir_hash,
        instrument_ids=instrument_ids,
        start=all_bar_days[0].isoformat(),
        end=all_bar_days[-1].isoformat(),
        frequency=frequency,
        initial_cash=float(initial_cash),
        lot_size=lot_size,
        metrics=metrics,
        equity_curve=curve,
        trades=_extract_trades(engine),
        positions=_extract_positions(engine),
        backtest_hash=backtest_hash(engine),
    )
