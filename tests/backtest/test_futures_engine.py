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
        margin_rate=D("0.1"),
        fee_rate=D("0.0002"),
        contract_multiplier=D("10"),
        initial_cash=D("100000"),
    )

    assert len(result.ledger.positions) == 1
    position = result.ledger.positions[0]
    assert position.direction is FuturesDirection.LONG
    assert position.quantity == 1
    # margin is not withdrawn; the fee is paid and settlement P&L is booked daily:
    # 100000 - 8 (open fee) + 1000 (d4 settle) + 1000 (d5 settle)
    assert result.ledger.cash == D("101992")
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
        margin_rate=D("0.1"),
        fee_rate=D("0.0002"),
        contract_multiplier=D("10"),
        initial_cash=D("100000"),
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
        margin_rate=D("0.1"),
        fee_rate=D("0.0002"),
        contract_multiplier=D("10"),
        initial_cash=D("100000"),
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
        margin_rate=D("0.1"),
        fee_rate=D("0.0002"),
        contract_multiplier=D("10"),
        initial_cash=D("100000"),
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
        margin_rate=D("0.1"),
        fee_rate=D("0.0002"),
        contract_multiplier=D("10"),
        initial_cash=D("100000"),
    )
    second = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={d(3): {"RB": (FuturesDirection.LONG, 1)}},
        margin_rate=D("0.1"),
        fee_rate=D("0.0002"),
        contract_multiplier=D("10"),
        initial_cash=D("100000"),
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


def test_close_today_uses_close_today_fee_offset() -> None:
    from quant_platform.backtest.futures_engine import (
        FuturesLedger,
        FuturesPosition,
        _apply_close,
    )
    from quant_platform.markets.futures import CloseOffset, FeeRate, FeeSchedule

    schedule = FeeSchedule(
        {
            CloseOffset.CLOSE_TODAY: FeeRate(per_lot=D("100"), ad_valorem=D("0")),
            CloseOffset.CLOSE_YESTERDAY: FeeRate(per_lot=D("1"), ad_valorem=D("0")),
        }
    )
    ledger = FuturesLedger(
        cash=D("100000"),
        positions=(
            FuturesPosition(
                instrument_id="RB",
                direction=FuturesDirection.LONG,
                quantity=1,
                average_price=D("4000"),
                opened_on=d(4),
            ),
        ),
        fills=(),
    )

    updated, ok = _apply_close(
        ledger,
        "RB",
        FuturesDirection.LONG,
        1,
        D("4000"),
        D("10"),
        d(4),
        D("0.0002"),
        schedule,
    )
    assert ok
    fill = updated.fills[-1]
    assert fill.close_offset is CloseOffset.CLOSE_TODAY
    assert fill.fee == D("100")


def test_delivery_policy_forces_exit() -> None:
    from quant_platform.markets.futures import DeliveryPolicy

    dates = (d(3), d(4), d(5), d(6))
    settle = {day: {"RB": D("4000")} for day in dates}
    opens = {
        d(4): {"RB": D("4000")},
        d(5): {"RB": D("4000")},
        d(6): {"RB": D("4000")},
    }

    result = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={
            d(3): {"RB": (FuturesDirection.LONG, 1)},
            d(4): {"RB": (FuturesDirection.LONG, 1)},
            d(5): {"RB": (FuturesDirection.LONG, 1)},
        },
        delivery_policies={
            "RB": DeliveryPolicy(force_exit_date=d(5), delivery_allowed=False)
        },
        margin_rate=D("0.1"),
        fee_rate=D("0.0002"),
        contract_multiplier=D("10"),
        initial_cash=D("100000"),
    )

    assert result.ledger.positions == ()
    assert len(result.ledger.fills) >= 2  # open fill + forced-exit close fill


def test_price_limit_blocks_fill() -> None:
    dates = (d(3), d(4))
    settle = {d(3): {"RB": D("4000")}, d(4): {"RB": D("4000")}}
    opens = {d(4): {"RB": D("4100")}}

    result = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={d(3): {"RB": (FuturesDirection.LONG, 1)}},
        price_limits={d(4): {"RB": (D("3900"), D("4000"))}},
        margin_rate=D("0.1"),
        fee_rate=D("0.0002"),
        contract_multiplier=D("10"),
        initial_cash=D("100000"),
    )

    assert result.ledger.positions == ()
    assert any(reason == "price_limit" for _, reason in result.blocked)


def test_forced_liquidation_on_margin_shortfall() -> None:
    dates = (d(3), d(4), d(5))
    settle = {
        d(3): {"RB": D("4000")},
        d(4): {"RB": D("3500")},
        d(5): {"RB": D("3500")},
    }
    opens = {d(4): {"RB": D("4000")}, d(5): {"RB": D("3500")}}

    result = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions={
            d(3): {"RB": (FuturesDirection.LONG, 1)},
            d(4): {"RB": (FuturesDirection.LONG, 1)},
        },
        margin_rate=D("0.1"),
        fee_rate=D("0"),
        contract_multiplier=D("10"),
        initial_cash=D("4500"),
    )

    assert result.ledger.positions == ()
    assert any(
        reason == "forced_liquidation" for _, reason in result.forced_liquidations
    )
