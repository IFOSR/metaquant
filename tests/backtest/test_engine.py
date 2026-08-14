from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from quant_platform.backtest.engine import run_a_share_backtest
from quant_platform.markets.cn_a import FillCertainty, TradabilityAssessment
from quant_platform.markets.contracts import MarketId
from quant_platform.markets.cost import EquityCostModel


def model() -> EquityCostModel:
    return EquityCostModel(
        model_id="cost://test/v1",
        market=MarketId.CN_A,
        commission_rate=0.0003,
        minimum_commission=5.0,
        stamp_duty_rate=0.0005,
        transfer_fee_rate=0.00001,
        slippage_bps=0.0,
        impact_bps_per_adv=0.0,
        funding_rate_daily=0.0,
        borrow_rate_daily=0.0,
    )


def blocked(reason: str) -> TradabilityAssessment:
    return TradabilityAssessment(FillCertainty.BLOCKED, reason)


def d(day: int) -> date:
    return date(2026, 8, day)


def test_buy_creates_position_at_next_open() -> None:
    dates = (d(3), d(4), d(5))
    close = {
        d(3): {"A": Decimal("10")},
        d(4): {"A": Decimal("11")},
        d(5): {"A": Decimal("12")},
    }
    opens = {d(4): {"A": Decimal("10.5")}, d(5): {"A": Decimal("11.5")}}

    result = run_a_share_backtest(
        trading_dates=dates,
        close_prices=close,
        open_prices=opens,
        target_weights={d(3): {"A": Decimal("0.5")}},
        tradability={},
        cost_model=model(),
        initial_cash=Decimal("100000"),
    )

    position = result.ledger.position("A")
    assert position is not None
    assert position.quantity > 0
    # filled at the T+1 open, not the T close
    assert result.ledger.fills[0].price == Decimal("10.5")


def test_t_plus_1_blocks_same_session_sell() -> None:
    dates = (d(3), d(4), d(5))
    close = {
        d(3): {"A": Decimal("10")},
        d(4): {"A": Decimal("11")},
        d(5): {"A": Decimal("12")},
    }
    opens = {d(4): {"A": Decimal("10")}, d(5): {"A": Decimal("11")}}

    result = run_a_share_backtest(
        trading_dates=dates,
        close_prices=close,
        open_prices=opens,
        target_weights={d(3): {"A": Decimal("0.5")}, d(4): {}},
        tradability={},
        cost_model=model(),
        initial_cash=Decimal("100000"),
    )

    # A was bought at d(4) open, so the d(4) sell is blocked by T+1
    assert any(b.reason == "t_plus_1" for b in result.blocked)
    assert result.ledger.position("A") is not None


def test_sell_liquidates_after_holding() -> None:
    dates = (d(3), d(4), d(5), d(6))
    close = {
        d(3): {"A": Decimal("10")},
        d(4): {"A": Decimal("11")},
        d(5): {"A": Decimal("12")},
        d(6): {"A": Decimal("13")},
    }
    opens = {
        d(4): {"A": Decimal("10")},
        d(5): {"A": Decimal("11")},
        d(6): {"A": Decimal("12")},
    }

    result = run_a_share_backtest(
        trading_dates=dates,
        close_prices=close,
        open_prices=opens,
        target_weights={
            d(3): {"A": Decimal("0.5")},
            d(4): {"A": Decimal("0.5")},
            d(5): {},
        },
        tradability={},
        cost_model=model(),
        initial_cash=Decimal("100000"),
    )

    # bought at d(4), held through d(5), sold into d(6)
    assert result.ledger.position("A") is None
    assert any(f.side.value == "SELL" for f in result.ledger.fills)


def test_price_limit_blocks_side() -> None:
    dates = (d(3), d(4), d(5))
    close = {
        d(3): {"A": Decimal("10")},
        d(4): {"A": Decimal("11")},
        d(5): {"A": Decimal("12")},
    }
    opens = {d(4): {"A": Decimal("10.5")}, d(5): {"A": Decimal("11.5")}}

    result = run_a_share_backtest(
        trading_dates=dates,
        close_prices=close,
        open_prices=opens,
        target_weights={d(3): {"A": Decimal("0.5")}},
        tradability={d(4): {"A": blocked("locked_upper_limit")}},
        cost_model=model(),
        initial_cash=Decimal("100000"),
    )

    assert any(b.reason == "tradability:locked_upper_limit" for b in result.blocked)
    assert result.ledger.position("A") is None


def test_costs_reduce_cash() -> None:
    dates = (d(3), d(4), d(5))
    close = {
        d(3): {"A": Decimal("10")},
        d(4): {"A": Decimal("10")},
        d(5): {"A": Decimal("10")},
    }
    opens = {d(4): {"A": Decimal("10")}, d(5): {"A": Decimal("10")}}

    result = run_a_share_backtest(
        trading_dates=dates,
        close_prices=close,
        open_prices=opens,
        target_weights={d(3): {"A": Decimal("0.5")}},
        tradability={},
        cost_model=model(),
        initial_cash=Decimal("100000"),
    )

    assert result.ledger.cash < Decimal("100000")
    assert result.ledger.fills[0].cost > Decimal("0")


def test_backtest_is_deterministic() -> None:
    dates = (d(3), d(4), d(5))
    close = {
        d(3): {"A": Decimal("10")},
        d(4): {"A": Decimal("11")},
        d(5): {"A": Decimal("12")},
    }
    opens = {d(4): {"A": Decimal("10.5")}, d(5): {"A": Decimal("11.5")}}
    weights = {d(3): {"A": Decimal("0.5")}, d(4): {"A": Decimal("0.4")}}

    first = run_a_share_backtest(
        trading_dates=dates,
        close_prices=close,
        open_prices=opens,
        target_weights=weights,
        tradability={},
        cost_model=model(),
        initial_cash=Decimal("100000"),
    )
    second = run_a_share_backtest(
        trading_dates=dates,
        close_prices=close,
        open_prices=opens,
        target_weights=weights,
        tradability={},
        cost_model=model(),
        initial_cash=Decimal("100000"),
    )

    assert first.content_hash() == second.content_hash()


def test_rejects_unordered_dates() -> None:
    with pytest.raises(ValueError):
        run_a_share_backtest(
            trading_dates=(d(5), d(4)),
            close_prices={},
            open_prices={},
            target_weights={},
            tradability={},
            cost_model=model(),
            initial_cash=Decimal("100000"),
        )
