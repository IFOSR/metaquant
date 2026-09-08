"""共享回测 runner：组装引擎 + SignalStrategy + 喂 bar + 提取结果。

复用 ``strategy_generation.backtest`` 里已有的 NT 装配与结果提取件
（成交/持仓提取、净值曲线采样、T+1 审计、结果 dataclass），只是把策略
构造从「load_strategy 完整 Strategy 子类」换成「load_signal_spec +
SignalStrategy」。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import BarType

from quant_platform.backtest.service import _CONTRACT_SPECS, _extract_positions, _underlying
from quant_platform.data_gateway.resolver import Bar
from quant_platform.markets.nt import (
    backtest_hash,
    build_equity_engine,
    build_futures_engine,
    equity_instrument,
    futures_contract,
    run_engine,
    to_nautilus_bars,
)
from quant_platform.markets.nt.venue import VenueSpec, venue_spec_for_market
from quant_platform.signal.contract import load_signal_spec
from quant_platform.signal.strategy import SignalStrategy
from quant_platform.strategy_generation.backtest import (
    _DEFAULT_FUTURES_FEE_SCHEDULE,
    _DEFAULT_INITIAL_CASH,
    _audit_t_plus_one,
    _bar_type_suffix,
    _equity_curve_recorder,
    _extract_strategy_trades,
    _normalize_instrument,
    _validate_market_instruments,
    StrategyBacktestResult,
    StrategyLoadError,
    bar_spec_for,
)


def run_signal_backtest(
    *,
    code: str,
    market: str,
    instrument_ids: tuple[str, ...],
    bars_by_instrument: dict[str, tuple[Bar, ...]],
    frequency: str,
    trend_bars_by_instrument: dict[str, tuple[Bar, ...]] | None = None,
    trend_frequency: str | None = None,
    initial_cash: Decimal = _DEFAULT_INITIAL_CASH,
    venue_spec: VenueSpec | None = None,
) -> StrategyBacktestResult:
    """运行信号 spec 回测，返回与旧策略回测兼容的 StrategyBacktestResult。"""
    _validate_market_instruments(market, instrument_ids)
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

    spec = load_signal_spec(code)
    resolved_venue_spec = venue_spec or venue_spec_for_market(
        market, futures_fee_schedule=_DEFAULT_FUTURES_FEE_SCHEDULE
    )
    bar_spec = bar_spec_for(frequency)
    bar_type_suffix = _bar_type_suffix(frequency)
    trend_bar_spec = bar_spec_for(trend_frequency) if trend_frequency else None
    trend_suffix = _bar_type_suffix(trend_frequency) if trend_frequency else None

    engine: Any = None
    all_nt_bars: list[Any] = []
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
        trend_bar_type_str = (
            f"{instrument.id}-{trend_suffix}" if trend_suffix else None
        )
        strategy = SignalStrategy(
            StrategyConfig(strategy_id=f"sig-{instrument.id.symbol}"),
            instrument_id=str(instrument.id),
            bar_type_str=bar_type_str,
            trend_bar_type_str=trend_bar_type_str,
            spec=spec,
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
