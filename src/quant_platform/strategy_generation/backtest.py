"""Execute a generated NautilusTrader strategy against historical bars (G19-P2/P3).

Loads untrusted strategy source (a ``Strategy`` subclass with the constructor
contract ``(instrument_id: str, bar_type_str: str)``), enforces the static
security policy, runs it on a NautilusTrader backtest engine wired with China
market fee models (net-of-fees cost basis), and returns a deterministic result
(equity curve + metrics + trades + positions + T+1 audit).
"""

from __future__ import annotations

import inspect
import math
import re
import time as _clock
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.currencies import CNY
from nautilus_trader.model.data import BarSpecification, BarType
from nautilus_trader.model.enums import BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.trading.strategy import Strategy

from quant_platform.backtest.service import (
    _CONTRACT_SPECS,
    _VENUE_BY_SUFFIX,
    BacktestMetrics,
    BacktestPosition,
    BacktestTrade,
    _extract_positions,
    _underlying,
)
from quant_platform.data_gateway.resolver import Bar
from quant_platform.markets.futures import CloseOffset, FeeRate, FeeSchedule
from quant_platform.markets.nt import (
    backtest_hash,
    build_equity_engine,
    build_futures_engine,
    day_bar_spec,
    equity_instrument,
    futures_contract,
    minute_bar_spec,
    run_engine,
    to_nautilus_bars,
)
from quant_platform.markets.nt.venue import (
    VenueSpec,
    venue_spec_for_market,
)
from quant_platform.strategy_generation.security import scan_strategy_source

_DEFAULT_INITIAL_CASH = Decimal("1000000")

SUPPORTED_FREQUENCIES = ("1d", "1w", "5m", "15m", "30m", "60m")


def _base_granularity(frequency: str) -> str:
    """回测频率 → 基础存储粒度：``1d``/``1w`` 用日线；分钟级统一用 5m。"""
    if frequency in ("1d", "1w"):
        return "1d"
    if frequency.endswith("m"):
        return "5m"
    raise StrategyLoadError(f"unsupported frequency: {frequency}")


def bar_spec_for(frequency: str) -> BarSpecification:
    """回测频率 → NautilusTrader bar 规格。"""
    if frequency == "1d":
        return day_bar_spec()
    if frequency == "1w":
        return BarSpecification(1, BarAggregation.WEEK, PriceType.LAST)
    if frequency.endswith("m"):
        return minute_bar_spec(int(frequency[:-1]))
    raise StrategyLoadError(f"unsupported frequency: {frequency}")


def _bar_type_suffix(frequency: str) -> str:
    if frequency == "1d":
        return "1-DAY-LAST-EXTERNAL"
    if frequency == "1w":
        return "1-WEEK-LAST-EXTERNAL"
    if frequency == "60m":
        return "1-HOUR-LAST-EXTERNAL"
    return f"{int(frequency[:-1])}-MINUTE-LAST-EXTERNAL"


def aggregate_bars(bars: tuple[Bar, ...], frequency: str) -> tuple[Bar, ...]:
    """把基础粒度 bars 聚合到目标频率（OHLC=首/最高/最低/收，量=求和）。

    - ``1d``/``5m``：原样返回（基础粒度）。
    - ``15m``/``30m``/``60m``：5m 向上聚合，按 bar 收盘时间向上取整分桶。
    - ``1w``：日线按 ISO 周聚合，桶标签取桶内最后一根 bar 的日期。
    """
    base = _base_granularity(frequency)
    if frequency == base:
        return bars
    buckets: dict[Any, list[Bar]] = {}
    order: list[Any] = []
    for bar in bars:
        ts = bar.timestamp
        key: Any
        if frequency == "1w":
            iso = ts.isocalendar()
            key = (iso.year, iso.week)
        else:
            minutes = int(frequency[:-1])
            epoch = int(ts.timestamp())
            key = -(-epoch // (minutes * 60)) * (minutes * 60)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(bar)
    aggregated: list[Bar] = []
    for key in order:
        group = buckets[key]
        aggregated.append(
            Bar(
                timestamp=group[-1].timestamp,
                open=group[0].open,
                high=max(item.high for item in group),
                low=min(item.low for item in group),
                close=group[-1].close,
                volume=sum(item.volume for item in group),
            )
        )
    return tuple(aggregated)


# 期货默认费率（演示口径，每手固定金额）；正式使用应传入市场规则层的
# FeeSchedule。开仓按平昨、未打 tag 的平仓单也按平昨计（与 G18 决策一致）。
_DEFAULT_FUTURES_FEE_SCHEDULE = FeeSchedule(
    {
        CloseOffset.CLOSE_TODAY: FeeRate(per_lot=Decimal("10")),
        CloseOffset.CLOSE_YESTERDAY: FeeRate(per_lot=Decimal("2")),
    }
)


class StrategyLoadError(RuntimeError):
    """Raised when generated strategy code cannot be compiled or instantiated."""


def load_strategy(
    code: str,
    *,
    instrument_id: str,
    bar_type_str: str,
    trend_bar_type_str: str | None = None,
) -> Strategy:
    """Compile and instantiate the generated ``Strategy`` subclass.

    The source must first pass the static security policy (import allowlist,
    forbidden calls, dunder-access ban) — LLM output is untrusted input.
    The generated code must define exactly one ``Strategy`` subclass whose
    ``__init__`` accepts ``(instrument_id: str, bar_type_str: str)``；多周期
    策略可再声明可选参数 ``trend_bar_type_str``（仅在声明时传入）。
    """
    violations = scan_strategy_source(code)
    if violations:
        raise StrategyLoadError(
            "strategy code rejected by security policy: " + "; ".join(violations)
        )
    namespace: dict[str, Any] = {
        "StrategyConfig": StrategyConfig,
        "Strategy": Strategy,
        "InstrumentId": InstrumentId,
        "BarType": BarType,
    }
    # 兼容旧生成代码：NautilusTrader 配置类是 pydantic 模型，类属性是
    # member_descriptor（返回器描述对象而非原始值）。把 `SomeConfig.attr`
    # 读成 `SomeConfig().attr`，让指标构造拿到真正的数值。新生成代码由
    # 静态检查拦截（agent 自动纠错），这里只为让已冻结的旧策略能加载。
    code = re.sub(r"\b([A-Z][A-Za-z0-9]*Config)\.([a-z_]\w*)", r"\1().\2", code)
    try:
        exec(compile(code, "<strategy>", "exec"), namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001
        raise StrategyLoadError(f"code failed to compile: {exc}") from exc
    strategy_cls: type[Strategy] | None = None
    for value in namespace.values():
        if (
            isinstance(value, type)
            and issubclass(value, Strategy)
            and value is not Strategy
        ):
            strategy_cls = value
            break
    if strategy_cls is None:
        raise StrategyLoadError("no Strategy subclass found in generated code")
    kwargs: dict[str, str] = {
        "instrument_id": instrument_id,
        "bar_type_str": bar_type_str,
    }
    params = inspect.signature(strategy_cls.__init__).parameters
    if trend_bar_type_str is not None and "trend_bar_type_str" in params:
        kwargs["trend_bar_type_str"] = trend_bar_type_str
    try:
        return strategy_cls(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise StrategyLoadError(f"strategy init failed: {exc}") from exc


def _normalize_instrument(instrument_id: str) -> tuple[str, str]:
    """规范化标的 ID：``600000.SH`` → (``600000``, ``SSE``)；期货同理。"""
    symbol, _, suffix = instrument_id.partition(".")
    suffix = suffix.upper()
    if suffix in ("SH", "SSE"):
        return symbol, "SSE"
    if suffix in ("SZ", "SZSE"):
        return symbol, "SZSE"
    venue = _VENUE_BY_SUFFIX.get(suffix)
    if venue is None or not symbol:
        raise StrategyLoadError(f"unsupported instrument_id: {instrument_id}")
    return symbol, venue


def db_instrument_id(instrument_id: str) -> str:
    """规范化到 PIT 存储里的标的 ID（``600000.SH`` → ``600000.SSE``）。

    A 股统一为 venue 名（SSE/SZSE）；期货库内沿用短后缀（``.SHF`` 等），
    保持原样不做 venue 改写。
    """
    symbol, venue = _normalize_instrument(instrument_id)
    if venue in ("SSE", "SZSE"):
        return f"{symbol}.{venue}"
    _, _, suffix = instrument_id.partition(".")
    return f"{symbol}.{suffix.upper()}"


def _extract_strategy_trades(engine: Any) -> tuple[BacktestTrade, ...]:
    """成交回报 + 逐笔费用（来自引擎 FeeModel，net 口径的基础）。"""
    fills = engine.trader.generate_order_fills_report()
    trades: list[BacktestTrade] = []
    for _, row in fills.iterrows():
        commissions = row["commissions"] or ()
        commission = sum(_money_amount(item) for item in commissions)
        trades.append(
            BacktestTrade(
                time=_ns_to_iso(row["ts_last"]),
                instrument_id=str(row["instrument_id"]),
                side=str(row["side"]),
                quantity=float(row["filled_qty"]),
                price=float(row["avg_px"]),
                commission=commission,
            )
        )
    return tuple(trades)


def _money_amount(value: object) -> float:
    """NautilusTrader Money 形如 ``"12.34 CNY"``。"""
    text = str(value)
    amount, _, _ = text.partition(" ")
    return float(amount.replace(",", "").replace("_", ""))


def _ns_to_iso(value: object) -> str:
    """NautilusTrader 报表时间戳：pandas Timestamp（datetime 子类）或纳秒整数。"""
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            nanoseconds = int(value)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return ""
        if nanoseconds <= 0:
            return ""
        return datetime.fromtimestamp(nanoseconds / 1e9, tz=UTC).isoformat()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat()


def _audit_t_plus_one(
    *,
    trades: tuple[BacktestTrade, ...],
    id_map: dict[str, str],
) -> tuple[str, ...]:
    """A 股 T+1 审计：卖出量超过当日开盘前持仓即违规（同日先买后卖）。

    日频 1d 下结构性不可能触发；5m 频率下 LLM 生成的策略可能违反。
    返回人类可读的违规描述列表（空 = 通过）。
    """
    events: list[tuple[datetime, str, str, int]] = []
    for trade in trades:
        user_id = id_map.get(trade.instrument_id, trade.instrument_id)
        try:
            symbol, venue = _normalize_instrument(user_id)
        except StrategyLoadError:
            continue  # 无法归一化的标的跳过（审计不阻断）
        if venue not in ("SSE", "SZSE"):
            continue  # 仅 A 股现货适用 T+1
        try:
            ts = datetime.fromisoformat(trade.time)
        except ValueError:
            continue
        signed = int(round(trade.quantity))
        events.append((ts, symbol, trade.side, signed))
    events.sort(key=lambda item: item[0])
    violations: list[str] = []
    position: dict[str, int] = {}
    overnight: dict[str, int] = {}
    current_date: date | None = None
    for ts, symbol, side, quantity in events:
        day = ts.date()
        if day != current_date:
            current_date = day
            overnight = {held: held_qty for held, held_qty in position.items()}
        if side == "BUY":
            position[symbol] = position.get(symbol, 0) + quantity
        else:
            sellable = max(0, overnight.get(symbol, 0))
            if quantity > sellable:
                violations.append(
                    f"t_plus_one_violation: {symbol} sold {quantity} on "
                    f"{day.isoformat()} exceeding {sellable} shares held "
                    "before the day"
                )
            position[symbol] = position.get(symbol, 0) - quantity
    return tuple(dict.fromkeys(violations))


def _equity_curve_recorder(
    *,
    engine: Any,
    exec_bar_type: BarType,
) -> Callable[..., tuple[tuple[tuple[str, float], ...], BacktestMetrics]]:
    """净值曲线直接从引擎出：逐 bar 用「引擎账户余额 + 引擎持仓盯市」采样。

    对齐 NT「结果从报告出」交互：不再从成交记录重建持仓、手搓盯市（删除
    双轨）。费用已计入账户余额；持仓浮盈用引擎持仓 × 乘数 × (收盘−开仓均价)
    盯市。逐 bar 订阅 ``data.bars.{exec_bar_type}`` 采样；返回的 finalize 在
    ``engine.run()`` 之后调用，用引擎最终状态 + 最后一根收盘价补一个终值点
    （覆盖末根 bar 上的成交）。
    """
    venue = next(iter(engine.list_venues()), Venue("SHFE"))
    points: list[tuple[datetime, float]] = []
    last_close = 0.0
    last_ts = 0

    def _mark(_close: float) -> float:
        # 引擎自己的组合权益（现金 + 持仓盯市），正确处理账户类型/乘数/费用。
        return float(engine.portfolio.equity(venue)[CNY])

    def _on_bar(msg: Any) -> None:
        nonlocal last_close, last_ts
        last_close = float(msg.close.as_double())
        last_ts = msg.ts_event
        points.append(
            (datetime.fromtimestamp(last_ts / 1e9, tz=UTC), _mark(last_close))
        )

    engine.kernel.msgbus.subscribe(topic=f"data.bars.{exec_bar_type}", handler=_on_bar)

    def finalize(
        initial_cash: Decimal,
        trade_count: int,
        aggregate_daily: bool,
    ) -> tuple[tuple[tuple[str, float], ...], BacktestMetrics]:
        if points:
            points.append(
                (datetime.fromtimestamp(last_ts / 1e9, tz=UTC), _mark(last_close))
            )
        if not points:
            return (), BacktestMetrics(0.0, None, 0.0, trade_count)

        if aggregate_daily:
            daily: dict[Any, float] = {}
            for ts, value in points:
                daily[ts.date()] = value
            points[:] = [
                (datetime.combine(day, time.max, tzinfo=UTC), value)
                for day, value in sorted(daily.items())
            ]

        curve: list[tuple[str, float]] = []
        returns: list[float] = []
        previous_equity = float(initial_cash)
        for ts, value in points:
            if previous_equity > 0:
                returns.append(value / previous_equity - 1.0)
            previous_equity = value
            curve.append((ts.date().isoformat(), value))

        final_equity = points[-1][1]
        total_return = final_equity / float(initial_cash) - 1.0
        sharpe: float | None = None
        if len(returns) >= 2:
            mean = sum(returns) / len(returns)
            variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
            if variance > 0:
                sharpe = mean / math.sqrt(variance) * math.sqrt(252)

        peak = float(initial_cash)
        max_drawdown = 0.0
        for _ts, value in points:
            peak = max(peak, value)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - value) / peak)
        return tuple(curve), BacktestMetrics(
            total_return, sharpe, max_drawdown, trade_count
        )

    return finalize


@dataclass(frozen=True, slots=True)
class StrategyBacktestResult:
    instrument_ids: tuple[str, ...]
    start: str
    end: str
    frequency: str
    initial_cash: float
    metrics: BacktestMetrics
    equity_curve: tuple[tuple[str, float], ...]
    trades: tuple[BacktestTrade, ...]
    positions: tuple[BacktestPosition, ...]
    backtest_hash: str
    error: str | None = None
    total_fees: float = 0.0
    constraint_violations: tuple[str, ...] = ()
    venue_spec: VenueSpec | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": "strategy-backtest/v1",
            "instrument_ids": list(self.instrument_ids),
            "start": self.start,
            "end": self.end,
            "frequency": self.frequency,
            "initial_cash": self.initial_cash,
            "cost_basis": "net_of_fees",
            "gross_of_fees": False,
            "total_fees": self.total_fees,
            "constraint_violations": list(self.constraint_violations),
            "metrics": self.metrics.payload(),
            "equity_curve": [
                {"date": day, "equity": equity} for day, equity in self.equity_curve
            ],
            "trades": [trade.payload() for trade in self.trades],
            "positions": [position.payload() for position in self.positions],
            "backtest_hash": self.backtest_hash,
            "venue_spec": self.venue_spec.payload() if self.venue_spec else None,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class BacktestRequest:
    """一次回测的声明式配置（对应 NT 的 config 对象，内容寻址）。

    venue_spec 承载全部执行假设（费用/撮合/延迟/种子/价格保护），回测与
    仿真共用同一份，保证「说的口径 = 跑的口径」。
    """

    draft_id: str
    market: str
    instrument_ids: tuple[str, ...]
    frequency: str
    trend_frequency: str | None
    start: date | None
    end: date | None
    initial_cash: Decimal
    venue_spec: VenueSpec

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "market": self.market,
            "instrument_ids": list(self.instrument_ids),
            "frequency": self.frequency,
            "trend_frequency": self.trend_frequency,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "initial_cash": str(self.initial_cash),
            "venue_spec": self.venue_spec.payload(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BacktestRequest:
        from quant_platform.markets.nt.venue import venue_spec_for_market

        start_raw = data.get("start")
        end_raw = data.get("end")
        market = data["market"]
        return cls(
            draft_id=str(data["draft_id"]),
            market=market,
            instrument_ids=tuple(data["instrument_ids"]),
            frequency=str(data["frequency"]),
            trend_frequency=data.get("trend_frequency"),
            start=date.fromisoformat(start_raw) if start_raw else None,
            end=date.fromisoformat(end_raw) if end_raw else None,
            initial_cash=Decimal(str(data["initial_cash"])),
            # 请求以声明式参数恢复；venue_spec 按市场取默认口径（自定义
            # 口径覆盖属矩阵扩展项，暂不参与持久化恢复）。
            venue_spec=venue_spec_for_market(market),
        )

    def content_hash(self) -> str:
        from quant_platform.experiments import canonical_hash

        return canonical_hash(self.to_dict())


def run_strategy_backtest(
    *,
    code: str,
    market: str,
    instrument_ids: tuple[str, ...],
    bars_by_instrument: dict[str, tuple[Bar, ...]],
    frequency: str,
    trend_bars_by_instrument: dict[str, tuple[Bar, ...]] | None = None,
    trend_frequency: str | None = None,
    initial_cash: Decimal = _DEFAULT_INITIAL_CASH,
    futures_fee_schedule: FeeSchedule = _DEFAULT_FUTURES_FEE_SCHEDULE,
    venue_spec: VenueSpec | None = None,
) -> StrategyBacktestResult:
    """Run the generated strategy on NautilusTrader against the given bars.

    ``frequency`` 为执行周期；``trend_frequency`` 为趋势周期（多周期策略，
    引擎会同时喂入两套 bar，策略通过 ``trend_bar_type_str`` 读取趋势指标）。
    成本口径为 net of fees：默认按市场装配完整 ``VenueSpec``（费用 + 涨跌停
    撮合，对齐 NT ``add_venue`` 交互），可传入自定义 ``venue_spec`` 覆盖。
    净值曲线直接从引擎账户/持仓盯市派生（删除手搓双轨）；结果同时附带 A 股
    T+1 同日回转审计与口径声明。
    """
    if market not in ("CN_A", "CN_COMMODITY_FUTURES"):
        raise StrategyLoadError(f"unsupported market: {market}")
    if frequency not in SUPPORTED_FREQUENCIES:
        raise StrategyLoadError(f"unsupported frequency: {frequency}")
    if trend_frequency is not None and trend_frequency not in SUPPORTED_FREQUENCIES:
        raise StrategyLoadError(f"unsupported trend frequency: {trend_frequency}")
    if not instrument_ids:
        raise StrategyLoadError("no instruments provided")
    venues = {_normalize_instrument(item)[1] for item in instrument_ids}
    if len(venues) != 1:
        raise StrategyLoadError("all instruments must share one venue")
    missing = [item for item in instrument_ids if item not in bars_by_instrument]
    if missing:
        raise StrategyLoadError(f"no market data for instruments: {', '.join(missing)}")
    if trend_frequency is not None:
        if trend_bars_by_instrument is None:
            raise StrategyLoadError("trend bars required for multi-timeframe strategy")
        missing_trend = [
            item for item in instrument_ids if item not in trend_bars_by_instrument
        ]
        if missing_trend:
            raise StrategyLoadError(
                "no trend market data for instruments: " + ", ".join(missing_trend)
            )

    resolved_venue_spec = venue_spec or venue_spec_for_market(
        market, futures_fee_schedule=futures_fee_schedule
    )
    bar_spec = bar_spec_for(frequency)
    bar_type_suffix = _bar_type_suffix(frequency)
    trend_bar_spec = bar_spec_for(trend_frequency) if trend_frequency else None
    trend_suffix = _bar_type_suffix(trend_frequency) if trend_frequency else None

    engine = None
    all_nt_bars = []
    id_map: dict[str, str] = {}
    exec_bar_type: BarType | None = None
    for instrument_id in instrument_ids:
        bars = bars_by_instrument[instrument_id]
        symbol, venue = _normalize_instrument(instrument_id)
        days = [bar.timestamp for bar in bars]
        if trend_bars_by_instrument is not None:
            days += [bar.timestamp for bar in trend_bars_by_instrument[instrument_id]]
        if venue in ("SSE", "SZSE"):
            instrument = equity_instrument(symbol=symbol, venue=venue)
            if engine is None:
                engine = build_equity_engine(
                    instrument=instrument,
                    initial_cash=initial_cash,
                    venue=venue,
                    venue_spec=resolved_venue_spec,
                )
            else:
                engine.add_instrument(instrument)
            precision = 2
        else:
            increment, multiplier, precision = _CONTRACT_SPECS.get(
                _underlying(symbol), _CONTRACT_SPECS["RB"]
            )
            instrument = futures_contract(
                symbol=symbol,
                venue=venue,
                underlying=_underlying(symbol),
                price_increment=increment,
                multiplier=multiplier,
                price_precision=precision,
                activation_ns=int((min(days) - timedelta(days=30)).timestamp() * 1e9),
                expiration_ns=int((max(days) + timedelta(days=120)).timestamp() * 1e9),
            )
            if engine is None:
                engine = build_futures_engine(
                    instrument=instrument,
                    initial_cash=initial_cash,
                    venue=venue,
                    venue_spec=resolved_venue_spec,
                )
            else:
                engine.add_instrument(instrument)

        bar_type_str = f"{instrument.id}-{bar_type_suffix}"
        id_map[str(instrument.id)] = instrument_id
        if exec_bar_type is None:
            exec_bar_type = BarType.from_str(bar_type_str)
        trend_bar_type_str = f"{instrument.id}-{trend_suffix}" if trend_suffix else None
        strategy = load_strategy(
            code,
            instrument_id=str(instrument.id),
            bar_type_str=bar_type_str,
            trend_bar_type_str=trend_bar_type_str,
        )
        engine.add_strategy(strategy)
        all_nt_bars.extend(
            to_nautilus_bars(
                bars,
                instrument_id=instrument.id,
                bar_spec=bar_spec,
                price_precision=precision,
            )
        )
        if trend_bars_by_instrument is not None and trend_bar_spec is not None:
            all_nt_bars.extend(
                to_nautilus_bars(
                    trend_bars_by_instrument[instrument_id],
                    instrument_id=instrument.id,
                    bar_spec=trend_bar_spec,
                    price_precision=precision,
                )
            )
    assert engine is not None
    assert exec_bar_type is not None

    finalize_curve = _equity_curve_recorder(engine=engine, exec_bar_type=exec_bar_type)
    run_engine(engine, bars=all_nt_bars)

    trades = _extract_strategy_trades(engine)
    total_fees = sum(trade.commission for trade in trades)
    curve, metrics = finalize_curve(
        initial_cash=initial_cash,
        trade_count=len(trades),
        aggregate_daily=frequency.endswith("m"),
    )
    violations = _audit_t_plus_one(trades=trades, id_map=id_map)
    all_bar_days = sorted(
        {bar.timestamp.date() for bars in bars_by_instrument.values() for bar in bars}
    )
    return StrategyBacktestResult(
        instrument_ids=instrument_ids,
        start=all_bar_days[0].isoformat(),
        end=all_bar_days[-1].isoformat(),
        frequency=frequency,
        initial_cash=float(initial_cash),
        metrics=metrics,
        equity_curve=curve,
        trades=trades,
        positions=_extract_positions(engine),
        backtest_hash=backtest_hash(engine),
        constraint_violations=violations,
        total_fees=total_fees,
        venue_spec=resolved_venue_spec,
    )


@dataclass(frozen=True, slots=True)
class CodeTestResult:
    """代码正确性测试结果（非回测）：编译 + 实例化 + 基础行情跑通。"""

    passed: bool
    exit_code: int
    stderr: str
    duration_ms: int

    def payload(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "exit_code": self.exit_code,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
        }


def code_test_strategy(
    *,
    code: str,
    market: str,
    instrument_ids: tuple[str, ...],
    bars_by_instrument: dict[str, tuple[Bar, ...]],
    frequency: str,
    trend_bars_by_instrument: dict[str, tuple[Bar, ...]] | None = None,
    trend_frequency: str | None = None,
    initial_cash: Decimal = _DEFAULT_INITIAL_CASH,
) -> CodeTestResult:
    """代码正确性测试：安全扫描 + 编译 + 实例化 + 用「数据准备」环节选定的
    基础行情端到端跑通。

    复用 ``run_strategy_backtest`` 的完整 NT 装配，喂入真实行情的一小段切片
    ——只要代码能通过安全扫描、编译、实例化，并在该数据上跑通不崩，即视为
    「代码正确」。它不衡量好坏（那是回测的事），只保证代码能跑。
    """
    started = _clock.monotonic()
    try:
        run_strategy_backtest(
            code=code,
            market=market,
            instrument_ids=instrument_ids,
            bars_by_instrument=bars_by_instrument,
            frequency=frequency,
            trend_bars_by_instrument=trend_bars_by_instrument,
            trend_frequency=trend_frequency,
            initial_cash=initial_cash,
        )
        passed = True
        exit_code = 0
        stderr = ""
    except Exception as exc:  # noqa: BLE001
        passed = False
        exit_code = 1
        stderr = str(exc)
    duration_ms = int((_clock.monotonic() - started) * 1000)
    return CodeTestResult(
        passed=passed, exit_code=exit_code, stderr=stderr, duration_ms=duration_ms
    )
