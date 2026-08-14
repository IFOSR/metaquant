from __future__ import annotations

from decimal import Decimal

import pytest

from quant_platform.markets.cn_a import (
    AShareDailyState,
    FillCertainty,
    OrderSide,
    SecurityStatus,
    check_price_collar,
    match_call_auction,
)

D = Decimal


def normal_state(**overrides: object) -> AShareDailyState:
    fields: dict[str, object] = {
        "halted": False,
        "volume": 1_000_000,
        "high": D("10.50"),
        "low": D("10.00"),
        "upper_limit": D("11.00"),
        "lower_limit": D("9.00"),
    }
    fields.update(overrides)
    return AShareDailyState(**fields)  # type: ignore[arg-type]


def test_st_blocks_buy_but_allows_sell() -> None:
    state = normal_state(security_status=SecurityStatus.ST)

    buy = state.assess(OrderSide.BUY)
    sell = state.assess(OrderSide.SELL)

    assert buy.certainty is FillCertainty.BLOCKED
    assert buy.reason == "st_buy_restriction"
    assert sell.certainty is FillCertainty.ELIGIBLE


def test_normal_status_is_tradable() -> None:
    assessment = normal_state().assess(OrderSide.BUY)

    assert assessment.certainty is FillCertainty.ELIGIBLE


def test_price_collar_buy_upper_bound() -> None:
    assert check_price_collar(D("10.20"), D("10.00"), OrderSide.BUY)
    assert not check_price_collar(D("10.21"), D("10.00"), OrderSide.BUY)


def test_price_collar_sell_lower_bound() -> None:
    assert check_price_collar(D("9.80"), D("10.00"), OrderSide.SELL)
    assert not check_price_collar(D("9.79"), D("10.00"), OrderSide.SELL)


def test_price_collar_rejects_nonpositive_prices() -> None:
    with pytest.raises(ValueError):
        check_price_collar(D("0"), D("10.00"), OrderSide.BUY)
    with pytest.raises(ValueError):
        check_price_collar(D("10.00"), D("-1"), OrderSide.BUY)


def test_call_auction_matches_max_volume() -> None:
    buys = ((D("10.00"), 100), (D("9.90"), 50))
    sells = ((D("10.00"), 80), (D("10.10"), 50))

    result = match_call_auction(buys, sells)

    # at 10.00: bids 100, asks 80 -> 80 matched; at 9.90: asks 0
    assert result.match_price == D("10.00")
    assert result.matched_quantity == 80


def test_call_auction_empty_orders() -> None:
    result = match_call_auction((), ((D("10.00"), 10),))

    assert result.match_price is None
    assert result.matched_quantity == 0


def test_call_auction_rejects_invalid_orders() -> None:
    with pytest.raises(ValueError):
        match_call_auction(((D("0"), 10),), ((D("10.00"), 10),))
