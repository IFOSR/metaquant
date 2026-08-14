from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from quant_platform.backtest.futures_engine import (
    FuturesDirection,
    run_futures_backtest,
)

D = Decimal


def d(day: int) -> date:
    return date(2026, 8, day)


def base_params() -> dict[str, Decimal]:
    return {
        "margin_rate": D("0.1"),
        "fee_rate": D("0.0002"),
        "contract_multiplier": D("10"),
        "initial_cash": D("100000"),
    }


def test_open_long_creates_position() -> None:
    dates = (d(3), d(4), d(5))
    settle = {d(3): {"RB": D("4000")}, d(4): {"RB": D("4100")}, d(5): {"RB": D("4200")}}
    opens = {d(4): {"RB": D("4000")}, d(5): {"RB": D("4100")}}

    result = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={
            d(3): {"RB": (FuturesDirection.LONG, 1)},
            d(4): {"RB": (FuturesDirection.LONG, 1)},
        },
        **base_params(),
    )

    assert len(result.ledger.positions) == 1
    position = result.ledger.positions[0]
    assert position.direction is FuturesDirection.LONG
    assert position.quantity == 1
    # margin is not withdrawn, but the fee is
    assert result.ledger.cash < D("100000")
    assert result.margin_used > D("0")


def test_short_position_direction() -> None:
    dates = (d(3), d(4), d(5))
    settle = {d(3): {"RB": D("4000")}, d(4): {"RB": D("4000")}, d(5): {"RB": D("4000")}}
    opens = {d(4): {"RB": D("4000")}, d(5): {"RB": D("4000")}}

    result = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={
            d(3): {"RB": (FuturesDirection.SHORT, 2)},
            d(4): {"RB": (FuturesDirection.SHORT, 2)},
        },
        **base_params(),
    )

    position = result.ledger.positions[0]
    assert position.direction is FuturesDirection.SHORT
    assert position.quantity == 2


def test_settle_records_nav_snapshot() -> None:
    dates = (d(3), d(4), d(5))
    settle = {d(3): {"RB": D("4000")}, d(4): {"RB": D("4100")}, d(5): {"RB": D("4200")}}
    opens = {d(4): {"RB": D("4000")}, d(5): {"RB": D("4100")}}

    result = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={
            d(3): {"RB": (FuturesDirection.LONG, 1)},
            d(4): {"RB": (FuturesDirection.LONG, 1)},
        },
        **base_params(),
    )

    # NAV snapshots reflect the rising settlement price (unrealized gain)
    assert len(result.ledger.nav_history) >= 2
    first_nav = result.ledger.nav_history[0][1]
    last_nav = result.ledger.nav_history[-1][1]
    assert last_nav > first_nav


def test_close_realizes_pnl() -> None:
    dates = (d(3), d(4), d(5))
    settle = {d(3): {"RB": D("4000")}, d(4): {"RB": D("4100")}, d(5): {"RB": D("4200")}}
    opens = {d(4): {"RB": D("4000")}, d(5): {"RB": D("4100")}}

    result = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={d(3): {"RB": (FuturesDirection.LONG, 1)}, d(4): {}},
        **base_params(),
    )

    # long 1 contract at 4000, closed at 4100, multiplier 10 -> +1000 P&L
    assert result.ledger.positions == ()
    # cash grew by the realized P&L (minus fees)
    assert result.ledger.cash > D("100000")


def test_insufficient_margin_blocked() -> None:
    dates = (d(3), d(4), d(5))
    settle = {d(3): {"RB": D("4000")}, d(4): {"RB": D("4000")}, d(5): {"RB": D("4000")}}
    opens = {d(4): {"RB": D("4000")}, d(5): {"RB": D("4000")}}

    result = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={d(3): {"RB": (FuturesDirection.LONG, 1)}},
        margin_rate=D("0.1"),
        fee_rate=D("0.0002"),
        contract_multiplier=D("10"),
        initial_cash=D("100"),  # margin alone is 4000
    )

    assert result.ledger.positions == ()
    assert any(reason == "insufficient_margin" for _, reason in result.blocked)


def test_backtest_is_deterministic() -> None:
    dates = (d(3), d(4), d(5))
    settle = {d(3): {"RB": D("4000")}, d(4): {"RB": D("4100")}, d(5): {"RB": D("4200")}}
    opens = {d(4): {"RB": D("4000")}, d(5): {"RB": D("4100")}}

    first = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={d(3): {"RB": (FuturesDirection.LONG, 1)}},
        **base_params(),
    )
    second = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={d(3): {"RB": (FuturesDirection.LONG, 1)}},
        **base_params(),
    )

    assert first.content_hash() == second.content_hash()


def test_rejects_nonpositive_margin_rate() -> None:
    dates = (d(3), d(4))
    with pytest.raises(ValueError):
        run_futures_backtest(
            trading_dates=dates,
            settlement_prices={},
            open_prices={},
            target_positions={},
            margin_rate=D("0"),
            fee_rate=D("0"),
            contract_multiplier=D("10"),
            initial_cash=D("100000"),
        )
