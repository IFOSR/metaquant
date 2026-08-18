"""backtest.service 单元测试（G18 NT 引擎 + 合成期货日频数据）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from quant_platform.backtest import run_factor_backtest
from quant_platform.data_gateway.models import PITRow
from quant_platform.experiments import FactorObservation

START = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
INSTRUMENTS = ("RB2610.SHF", "AU2612.SHF")


def _pit_row(instrument: str, field: str, day: int, value: float) -> PITRow:
    ts = START + timedelta(days=day)
    return PITRow(
        dataset_id="market-eod",
        field=f"market.eod.{field}",
        instrument_id=instrument,
        event_time=ts,
        available_time=ts,
        ingested_at=ts,
        revision_id="test",
        source_id="test",
        license_tag="licensed-research",
        value=value,
    )


def _snapshot_rows(days: int = 10) -> tuple[PITRow, ...]:
    rows: list[PITRow] = []
    for day in range(days):
        for index, instrument in enumerate(INSTRUMENTS):
            base = 3000.0 + index * 1000.0
            close = base + day * 10.0  # 两个合约都单调上涨
            rows.append(_pit_row(instrument, "close", day, close))
            rows.append(_pit_row(instrument, "volume", day, 1000.0))
    return tuple(rows)


def _observations(values: dict[tuple[str, int], float | None]) -> tuple[FactorObservation, ...]:
    return tuple(
        FactorObservation(instrument, START + timedelta(days=day), value)
        for (instrument, day), value in sorted(values.items())
    )


class TestRunFactorBacktest:
    def test_long_only_when_all_signals_positive(self) -> None:
        observations = _observations(
            {
                (instrument, day): 0.01
                for instrument in INSTRUMENTS
                for day in range(9)
            }
        )
        result = run_factor_backtest(
            factor_ir_hash="a" * 64,
            observations=observations,
            snapshot_rows=_snapshot_rows(),
        )

        assert result.instrument_ids == tuple(sorted(INSTRUMENTS))
        assert len(result.equity_curve) == 10
        # 价格单调上涨、始终做多 → 净值单调不减，总收益为正
        equities = [equity for _, equity in result.equity_curve]
        assert equities == sorted(equities)
        assert result.metrics.total_return > 0
        assert result.metrics.max_drawdown == 0.0
        assert result.metrics.trade_count == 2  # 每个合约各开一次多仓

    def test_short_position_profits_when_price_falls(self) -> None:
        rows: list[PITRow] = []
        for day in range(10):
            rows.append(_pit_row("RB2610.SHF", "close", day, 3000.0 - day * 10.0))
        observations = _observations({("RB2610.SHF", day): -0.01 for day in range(9)})

        result = run_factor_backtest(
            factor_ir_hash="b" * 64,
            observations=observations,
            snapshot_rows=tuple(rows),
            instrument_ids=("RB2610.SHF",),
        )

        assert result.metrics.total_return > 0

    def test_flat_when_no_prior_signal(self) -> None:
        # 因子值只在最后一天出现 → 没有任何 bar 能用到它 → 不开仓
        observations = _observations({("RB2610.SHF", 9): 0.5})
        result = run_factor_backtest(
            factor_ir_hash="c" * 64,
            observations=observations,
            snapshot_rows=_snapshot_rows(),
            instrument_ids=("RB2610.SHF",),
        )
        assert result.metrics.trade_count == 0
        assert result.metrics.total_return == 0.0

    def test_deterministic_replay_hash(self) -> None:
        observations = _observations(
            {
                (instrument, day): 0.01 if day % 2 == 0 else -0.01
                for instrument in INSTRUMENTS
                for day in range(9)
            }
        )
        kwargs = dict(
            factor_ir_hash="d" * 64,
            observations=observations,
            snapshot_rows=_snapshot_rows(),
        )
        first = run_factor_backtest(**kwargs)
        second = run_factor_backtest(**kwargs)
        assert first.backtest_hash == second.backtest_hash
        assert first.equity_curve == second.equity_curve

    def test_missing_market_data_raises(self) -> None:
        observations = _observations({("RB2610.SHF", 1): 0.1})
        with pytest.raises(ValueError, match="no market data"):
            run_factor_backtest(
                factor_ir_hash="e" * 64,
                observations=observations,
                snapshot_rows=_snapshot_rows(),
                instrument_ids=("RB2610.SHF", "CU2609.SHF"),
            )

    def test_initial_cash_scales_equity(self) -> None:
        observations = _observations({("RB2610.SHF", day): 0.01 for day in range(9)})
        result = run_factor_backtest(
            factor_ir_hash="f" * 64,
            observations=observations,
            snapshot_rows=_snapshot_rows(),
            instrument_ids=("RB2610.SHF",),
            initial_cash=Decimal("1000000"),
        )
        assert result.equity_curve[0][1] == pytest.approx(1000000.0)

    def test_window_filter_limits_backtest_period(self) -> None:
        observations = _observations({("RB2610.SHF", day): 0.01 for day in range(9)})
        result = run_factor_backtest(
            factor_ir_hash="0" * 64,
            observations=observations,
            snapshot_rows=_snapshot_rows(),
            instrument_ids=("RB2610.SHF",),
            start=START.date() + timedelta(days=4),
            end=START.date() + timedelta(days=7),
        )
        assert result.start == "2026-08-05"
        assert result.end == "2026-08-08"
        assert len(result.equity_curve) == 4

    def test_minute_frequency_aggregates_equity_daily(self) -> None:
        # 每天 3 根 5m bar（market.minute.* 字段），单调上涨
        rows: list[PITRow] = []
        for day in range(4):
            for bar_index in range(3):
                ts = (
                    START
                    + timedelta(days=day)
                    - timedelta(hours=1)
                    + timedelta(minutes=5 * bar_index)
                )
                rows.append(
                    PITRow(
                        dataset_id="market-minute",
                        field="market.minute.close",
                        instrument_id="RB2610.SHF",
                        event_time=ts,
                        available_time=ts,
                        ingested_at=ts,
                        revision_id="test",
                        source_id="test",
                        license_tag="licensed-research",
                        value=3000.0 + day * 10.0 + bar_index,
                    )
                )
        observations = _observations({("RB2610.SHF", day): 0.01 for day in range(3)})
        result = run_factor_backtest(
            factor_ir_hash="2" * 64,
            observations=observations,
            snapshot_rows=tuple(rows),
            instrument_ids=("RB2610.SHF",),
            frequency="5m",
        )
        assert result.frequency == "5m"
        assert len(result.equity_curve) == 4  # 按日聚合
        assert result.metrics.total_return > 0
        assert result.metrics.trade_count == 1  # 只开一次多仓

    def test_trades_and_positions_exposed(self) -> None:
        # 多空交替信号 → 每天换向，产生成交与已平仓回合
        observations = _observations(
            {("RB2610.SHF", day): 0.01 if day % 2 == 0 else -0.01 for day in range(9)}
        )
        result = run_factor_backtest(
            factor_ir_hash="1" * 64,
            observations=observations,
            snapshot_rows=_snapshot_rows(),
            instrument_ids=("RB2610.SHF",),
        )
        assert result.trades
        first = result.trades[0]
        assert first.instrument_id == "RB2610.SHFE"
        assert first.side in ("BUY", "SELL")
        assert first.quantity >= 1
        assert first.price > 0
        assert first.time
        closed = [p for p in result.positions if p.closed_at is not None]
        assert closed
        assert all(p.avg_px_close is not None for p in closed)
        # 多头回合在上涨行情中应盈利
        long_rounds = [p for p in closed if p.entry == "BUY"]
        assert long_rounds and all(p.realized_pnl > 0 for p in long_rounds)
