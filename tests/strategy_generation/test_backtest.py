"""Tests for executing generated NautilusTrader strategies (G19-P2/P3)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from quant_platform.backtest.service import BacktestTrade
from quant_platform.data_gateway.resolver import Bar
from quant_platform.strategy_generation.backtest import (
    StrategyLoadError,
    _audit_t_plus_one,
    aggregate_bars,
    code_test_strategy,
    load_strategy,
    run_strategy_backtest,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")

_EMA_CROSS = """\
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy


class GenStrategy(Strategy):
    def __init__(self, instrument_id: str, bar_type_str: str):
        super().__init__(StrategyConfig(strategy_id="GEN-001"))
        self._instrument_id = InstrumentId.from_str(instrument_id)
        self._bar_type = BarType.from_str(bar_type_str)
        self.fast = ExponentialMovingAverage(2)
        self.slow = ExponentialMovingAverage(3)

    def on_start(self):
        self.register_indicator_for_bars(self._bar_type, self.fast)
        self.register_indicator_for_bars(self._bar_type, self.slow)
        self.subscribe_bars(self._bar_type)

    def on_bar(self, bar):
        if not self.indicators_initialized():
            return
        if self.fast.value >= self.slow.value:
            if self.portfolio.is_flat(self._instrument_id):
                self._market(OrderSide.BUY, 100)
        else:
            if self.portfolio.is_net_long(self._instrument_id):
                self._market(OrderSide.SELL, 100)

    def _market(self, side, qty):
        instrument = self.cache.instrument(self._instrument_id)
        if instrument is None:
            return
        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=side,
            quantity=instrument.make_qty(qty),
        )
        self.submit_order(order)
"""


def _daily_bars(days: int = 30) -> tuple[Bar, ...]:
    base = datetime(2026, 1, 5, 15, 0, tzinfo=SHANGHAI)
    price = 10.0
    bars: list[Bar] = []
    for i in range(days):
        price += 0.1
        bars.append(
            Bar(
                timestamp=base + timedelta(days=i),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1000.0,
            )
        )
    return tuple(bars)


def test_load_strategy_instantiates() -> None:
    strategy = load_strategy(
        _EMA_CROSS,
        instrument_id="600000.SSE",
        bar_type_str="600000.SSE-1-DAY-LAST-EXTERNAL",
    )
    assert strategy is not None


def test_load_strategy_tolerates_config_class_attr_read() -> None:
    """旧生成代码读 `SomeConfig.attr`（pydantic 类属性非原始值）也应能加载。"""
    code = (
        "from nautilus_trader.config import StrategyConfig\n"
        "from nautilus_trader.trading.strategy import Strategy\n"
        "from nautilus_trader.model.identifiers import InstrumentId\n"
        "from nautilus_trader.model.data import BarType\n"
        "from nautilus_trader.indicators import SimpleMovingAverage\n"
        "class MyConfig(StrategyConfig):\n"
        "    ma_period: int = 20\n"
        "class C(Strategy):\n"
        "    def __init__(self, instrument_id: str, bar_type_str: str):\n"
        "        super().__init__(StrategyConfig(strategy_id='GEN'))\n"
        "        self._i = InstrumentId.from_str(instrument_id)\n"
        "        self._b = BarType.from_str(bar_type_str)\n"
        "        self._ma = SimpleMovingAverage(MyConfig.ma_period)\n"
    )
    strategy = load_strategy(
        code,
        instrument_id="600000.SSE",
        bar_type_str="600000.SSE-1-DAY-LAST-EXTERNAL",
    )
    assert strategy is not None


def test_load_strategy_rejects_non_strategy_code() -> None:
    with pytest.raises(StrategyLoadError):
        load_strategy(
            "x = 1\n",
            instrument_id="600000.SSE",
            bar_type_str="600000.SSE-1-DAY-LAST-EXTERNAL",
        )


def test_run_strategy_backtest_buys_and_holds() -> None:
    bars = _daily_bars()
    result = run_strategy_backtest(
        code=_EMA_CROSS,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": bars},
        frequency="1d",
        initial_cash=Decimal("1000000"),
    )
    assert result.trades
    assert result.equity_curve
    assert result.metrics.trade_count >= 1
    assert len(result.backtest_hash) == 64
    assert result.positions


def test_equity_curve_from_engine_is_consistent_with_final_equity() -> None:
    """净值曲线从引擎出：末点必须等于引擎最终组合权益（不自相矛盾）。"""
    bars = _daily_bars()
    result = run_strategy_backtest(
        code=_EMA_CROSS,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": bars},
        frequency="1d",
        initial_cash=Decimal("1000000"),
    )
    assert result.equity_curve
    assert result.metrics.total_return == pytest.approx(
        result.equity_curve[-1][1] / 1_000_000 - 1.0
    )
    # 口径声明：net of fees + 中国市场费用/涨跌停撮合
    assert result.venue_spec is not None
    assert result.venue_spec.payload()["cost_basis"] == "net_of_fees"
    assert result.venue_spec.payload()["fee_model"] == "AShareFeeModel"
    assert result.venue_spec.payload()["fill_model"] == "PriceLimitFillModel"


def test_run_strategy_backtest_is_net_of_fees() -> None:
    bars = _daily_bars()
    result = run_strategy_backtest(
        code=_EMA_CROSS,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": bars},
        frequency="1d",
        initial_cash=Decimal("1000000"),
    )
    assert result.total_fees > 0
    assert any(trade.commission > 0 for trade in result.trades)
    payload = result.payload()
    assert payload["cost_basis"] == "net_of_fees"
    assert payload["gross_of_fees"] is False
    assert payload["total_fees"] == pytest.approx(result.total_fees)


def test_load_strategy_rejects_policy_violations() -> None:
    with pytest.raises(StrategyLoadError, match="security policy"):
        load_strategy(
            "import os\n" + _EMA_CROSS,
            instrument_id="600000.SSE",
            bar_type_str="600000.SSE-1-DAY-LAST-EXTERNAL",
        )


def test_t_plus_one_audit_flags_same_day_round_trip() -> None:
    day = datetime(2026, 1, 5, 9, 35, tzinfo=SHANGHAI)
    trades = (
        BacktestTrade(
            time=day.isoformat(),
            instrument_id="600000.SSE",
            side="BUY",
            quantity=100,
            price=10.0,
        ),
        BacktestTrade(
            time=day.isoformat(),
            instrument_id="600000.SSE",
            side="SELL",
            quantity=100,
            price=10.1,
        ),
    )
    violations = _audit_t_plus_one(trades=trades, id_map={})
    assert violations
    assert "t_plus_one_violation" in violations[0]


def test_t_plus_one_audit_allows_next_day_exit() -> None:
    day_one = datetime(2026, 1, 5, 15, 0, tzinfo=SHANGHAI)
    day_two = datetime(2026, 1, 6, 15, 0, tzinfo=SHANGHAI)
    trades = (
        BacktestTrade(
            time=day_one.isoformat(),
            instrument_id="600000.SSE",
            side="BUY",
            quantity=100,
            price=10.0,
        ),
        BacktestTrade(
            time=day_two.isoformat(),
            instrument_id="600000.SSE",
            side="SELL",
            quantity=100,
            price=10.1,
        ),
    )
    assert _audit_t_plus_one(trades=trades, id_map={}) == ()


def test_run_strategy_backtest_requires_data() -> None:
    with pytest.raises(StrategyLoadError):
        run_strategy_backtest(
            code=_EMA_CROSS,
            market="CN_A",
            instrument_ids=("600000.SH",),
            bars_by_instrument={},
            frequency="1d",
        )


def test_code_test_strategy_passes_valid_strategy() -> None:
    """代码正确性测试：合法策略应在基础行情上跑通。"""
    result = code_test_strategy(
        code=_EMA_CROSS,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": _daily_bars(30)},
        frequency="1d",
    )
    assert result.passed is True
    assert result.exit_code == 0
    assert result.duration_ms >= 0


def test_code_test_strategy_fails_policy_violation() -> None:
    """代码正确性测试：违反安全策略的代码必须被拦截。"""
    result = code_test_strategy(
        code="import os\n" + _EMA_CROSS,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": _daily_bars(30)},
        frequency="1d",
    )
    assert result.passed is False
    assert result.exit_code != 0
    assert "security policy" in result.stderr


# ── 任意周期：聚合 / 周线 / 多周期 / 多标的（P2/P3）─────────────────────────


def _minute_bars(days: int = 5, bars_per_day: int = 6) -> tuple[Bar, ...]:
    """每个交易日 6 根 5m bar（09:05 ~ 09:30），价格缓涨。"""
    base = datetime(2026, 1, 5, 9, 5, tzinfo=SHANGHAI)
    bars: list[Bar] = []
    price = 10.0
    for day in range(days):
        for index in range(bars_per_day):
            price += 0.05
            ts = base + timedelta(days=day, minutes=5 * index)
            bars.append(
                Bar(
                    timestamp=ts,
                    open=price,
                    high=price + 0.02,
                    low=price - 0.02,
                    close=price,
                    volume=100.0,
                )
            )
    return tuple(bars)


def test_aggregate_bars_5m_to_15m() -> None:
    bars = _minute_bars(days=1, bars_per_day=6)
    aggregated = aggregate_bars(bars, "15m")
    assert len(aggregated) == 2  # 6 根 5m → 2 根 15m
    first = aggregated[0]
    assert first.open == bars[0].open
    assert first.close == bars[2].close
    assert first.high == max(bar.high for bar in bars[:3])
    assert first.low == min(bar.low for bar in bars[:3])
    assert first.volume == sum(bar.volume for bar in bars[:3])


def test_aggregate_bars_daily_to_weekly() -> None:
    bars = _daily_bars(14)  # 两周日线
    aggregated = aggregate_bars(bars, "1w")
    assert 1 < len(aggregated) < 14
    assert aggregated[0].open == bars[0].open
    assert all(
        aggregated[i].timestamp <= aggregated[i + 1].timestamp
        for i in range(len(aggregated) - 1)
    )


def test_aggregate_bars_passthrough_base() -> None:
    bars = _daily_bars(5)
    assert aggregate_bars(bars, "1d") == bars
    minute = _minute_bars(days=1)
    assert aggregate_bars(minute, "5m") == minute


def test_run_strategy_backtest_weekly_frequency() -> None:
    result = run_strategy_backtest(
        code=_EMA_CROSS,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": aggregate_bars(_daily_bars(40), "1w")},
        frequency="1w",
        initial_cash=Decimal("1000000"),
    )
    assert result.error is None
    assert result.trades
    assert result.equity_curve


def test_run_strategy_backtest_multi_instrument_shared_account() -> None:
    """多标的组合回测：同一市场的两个标的共用一个账户，各自独立跑策略。"""
    result = run_strategy_backtest(
        code=_EMA_CROSS,
        market="CN_A",
        instrument_ids=("600000.SH", "600519.SH"),
        bars_by_instrument={
            "600000.SH": _daily_bars(),
            "600519.SH": _daily_bars(),
        },
        frequency="1d",
        initial_cash=Decimal("1000000"),
    )
    assert result.error is None
    assert result.trades
    assert len(result.equity_curve) > 0
    traded = {trade.instrument_id for trade in result.trades}
    assert traded == {"600000.SSE", "600519.SSE"}


def test_run_strategy_backtest_rejects_mixed_venues() -> None:
    """跨市场（SSE + SZSE）多标的暂不支持，给出明确错误。"""
    with pytest.raises(StrategyLoadError, match="share one venue"):
        run_strategy_backtest(
            code=_EMA_CROSS,
            market="CN_A",
            instrument_ids=("600000.SH", "000001.SZ"),
            bars_by_instrument={
                "600000.SH": _daily_bars(),
                "000001.SZ": _daily_bars(),
            },
            frequency="1d",
        )


_MTF = """\
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators import SimpleMovingAverage
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy


class MtfStrategy(Strategy):
    def __init__(self, instrument_id: str, bar_type_str: str,
                 trend_bar_type_str: str | None = None):
        super().__init__(StrategyConfig(strategy_id="GEN-MTF"))
        self._instrument_id = InstrumentId.from_str(instrument_id)
        self._bar_type = BarType.from_str(bar_type_str)
        self._trend_bar_type = (
            BarType.from_str(trend_bar_type_str) if trend_bar_type_str else None
        )
        self.trend_sma = SimpleMovingAverage(3)

    def on_start(self):
        self.subscribe_bars(self._bar_type)
        if self._trend_bar_type is not None:
            self.register_indicator_for_bars(self._trend_bar_type, self.trend_sma)
            self.subscribe_bars(self._trend_bar_type)

    def on_bar(self, bar):
        if self._trend_bar_type is not None and bar.bar_type == self._trend_bar_type:
            return
        # 只有趋势指标就绪（证明趋势 bar 已到）才允许交易
        if self._trend_bar_type is not None and not self.trend_sma.initialized:
            return
        if self.portfolio.is_flat(self._instrument_id):
            instrument = self.cache.instrument(self._instrument_id)
            if instrument is None:
                return
            order = self.order_factory.market(
                instrument_id=self._instrument_id,
                order_side=OrderSide.BUY,
                quantity=instrument.make_qty(100),
            )
            self.submit_order(order)
"""


def test_load_strategy_passes_trend_bar_type() -> None:
    strategy = load_strategy(
        _MTF,
        instrument_id="600000.SSE",
        bar_type_str="600000.SSE-5-MINUTE-LAST-EXTERNAL",
        trend_bar_type_str="600000.SSE-1-DAY-LAST-EXTERNAL",
    )
    assert strategy is not None


def test_run_strategy_backtest_multi_timeframe() -> None:
    """日线趋势 + 5m 执行：趋势 bar 到达后（SMA 就绪）策略才买入。"""
    exec_bars = _minute_bars(days=6)
    trend_bars = _daily_bars(10)
    result = run_strategy_backtest(
        code=_MTF,
        market="CN_A",
        instrument_ids=("600000.SH",),
        bars_by_instrument={"600000.SH": exec_bars},
        frequency="5m",
        trend_bars_by_instrument={"600000.SH": trend_bars},
        trend_frequency="1d",
        initial_cash=Decimal("1000000"),
    )
    assert result.error is None
    # 趋势 SMA(3) 需 3 根日线就绪后才买入 —— 有成交即证明趋势 bar 被喂入
    assert result.trades
