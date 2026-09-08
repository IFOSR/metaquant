from __future__ import annotations

from quant_platform.strategy_generation.backtest_context import (
    format_backtest_context,
)


def test_format_backtest_context_contains_analysis_fields() -> None:
    payload = {
        "instrument_ids": ["SA8888.CZCE"],
        "start": "2026-03-07",
        "end": "2026-09-07",
        "frequency": "15m",
        "initial_cash": 1_000_000,
        "gross_of_fees": False,
        "venue_spec": {
            "market": "CN_COMMODITY_FUTURES",
            "cost_basis": "net_of_fees",
            "fee_model": "FuturesFeeModel",
        },
        "metrics": {
            "total_return": -0.023,
            "sharpe": -0.4,
            "max_drawdown": 0.08,
            "trade_count": 4,
        },
        "total_fees": 128.0,
        "trades": [
            {
                "time": "2026-05-07T05:45:00+00:00",
                "instrument_id": "SA8888.CZCE",
                "side": "BUY",
                "quantity": 1,
                "price": 1264,
                "action": "开多",
            }
        ],
        "positions": [
            {
                "instrument_id": "SA8888.CZCE",
                "entry": "BUY",
                "peak_qty": 1,
                "avg_px_open": 1264,
                "avg_px_close": 1261,
                "realized_pnl": -64,
                "opened_at": "2026-05-07T05:45:00+00:00",
                "closed_at": "2026-05-07T13:30:00+00:00",
            }
        ],
        "equity_curve": [
            {"date": "2026-03-07T01:00:00+00:00", "equity": 1_000_000},
            {"date": "2026-09-07T01:00:00+00:00", "equity": 977_000},
        ],
    }

    context = format_backtest_context(
        payload,
        backtest_hash="hash-context-1",
        market="CN_COMMODITY_FUTURES",
    )

    assert "[导入的历史回测结果]" in context
    assert "hash-context-1" in context
    assert "SA8888.CZCE" in context
    assert "net_of_fees" in context
    assert "总收益" in context
    assert "-2.30%" in context
    assert "开多" in context
    assert "已实现盈亏" in context
    assert "2026-03-07T01:00:00+00:00" in context
    assert "[回测结果结束]" in context


def test_format_backtest_context_bounds_equity_curve_samples() -> None:
    curve = [
        {"date": f"2026-01-{day:02d}T00:00:00+00:00", "equity": day}
        for day in range(1, 151)
    ]
    payload = {
        "metrics": {},
        "trades": [],
        "positions": [],
        "equity_curve": curve,
    }

    context = format_backtest_context(
        payload,
        backtest_hash="hash-large",
        market="CN_A",
        max_equity_points=12,
    )

    assert context.count("2026-01-") == 12
    assert "2026-01-01T00:00:00+00:00" in context
    assert "2026-01-02T00:00:00+00:00" not in context
