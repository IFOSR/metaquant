from __future__ import annotations

import pytest

from quant_platform.markets.cn_a import OrderSide
from quant_platform.markets.contracts import MarketId
from quant_platform.markets.cost import (
    EquityCostModel,
    FuturesCostModel,
    InMemoryCostModelCatalog,
)


def equity() -> EquityCostModel:
    return EquityCostModel(
        model_id="cost://cn-a-default/v1",
        market=MarketId.CN_A,
        commission_rate=0.0003,
        minimum_commission=5.0,
        stamp_duty_rate=0.0005,
        transfer_fee_rate=0.00001,
        slippage_bps=5.0,
        impact_bps_per_adv=10.0,
        funding_rate_daily=0.0002,
        borrow_rate_daily=0.0005,
    )


def futures() -> FuturesCostModel:
    return FuturesCostModel(
        model_id="cost://futures-default/v1",
        market=MarketId.CN_COMMODITY_FUTURES,
        fee_rate=0.0002,
        slippage_bps=2.0,
        impact_bps_per_adv=8.0,
        margin_rate=0.1,
        funding_rate_daily=0.0001,
    )


def test_equity_stamp_duty_only_on_sell() -> None:
    model = equity()
    notional = 100_000.0

    buy = model.single_side_cost(OrderSide.BUY, notional)
    sell = model.single_side_cost(OrderSide.SELL, notional)

    # stamp duty is exactly notional * rate on sell only
    assert sell - buy == pytest.approx(notional * 0.0005)


def test_equity_minimum_commission_applies() -> None:
    model = equity()
    tiny = 100.0  # commission 0.03 < minimum 5.0

    cost = model.single_side_cost(OrderSide.BUY, tiny)

    assert cost >= 5.0


def test_equity_impact_scales_with_participation() -> None:
    model = equity()
    notional = 10_000.0

    low = model.impact_cost(notional, adv=10_000_000.0)
    high = model.impact_cost(notional, adv=100_000.0)

    assert high > low


def test_equity_round_trip_without_adv() -> None:
    model = equity()
    notional = 100_000.0

    cost = model.round_trip_cost(notional)

    expected = model.single_side_cost(
        OrderSide.BUY, notional
    ) + model.single_side_cost(OrderSide.SELL, notional)
    assert cost == pytest.approx(expected)


def test_futures_margin_requirement() -> None:
    model = futures()

    assert model.margin_requirement(1_000_000.0) == pytest.approx(100_000.0)


def test_futures_round_trip() -> None:
    model = futures()
    notional = 500_000.0

    cost = model.round_trip_cost(notional)

    assert cost == pytest.approx(2.0 * model.single_side_cost(notional))


def test_models_are_deterministic() -> None:
    assert equity().content_hash() == equity().content_hash()
    assert futures().content_hash() == futures().content_hash()


def test_rejects_wrong_market() -> None:
    with pytest.raises(ValueError):
        EquityCostModel(
            model_id="bad",
            market=MarketId.CN_COMMODITY_FUTURES,
            commission_rate=0.0003,
            minimum_commission=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
            slippage_bps=5.0,
            impact_bps_per_adv=10.0,
            funding_rate_daily=0.0002,
            borrow_rate_daily=0.0005,
        )


def test_rejects_negative_rate() -> None:
    with pytest.raises(ValueError):
        FuturesCostModel(
            model_id="bad",
            market=MarketId.CN_COMMODITY_FUTURES,
            fee_rate=-0.1,
            slippage_bps=2.0,
            impact_bps_per_adv=8.0,
            margin_rate=0.1,
            funding_rate_daily=0.0001,
        )


def test_catalog_resolves_and_fails_closed() -> None:
    catalog = InMemoryCostModelCatalog((equity(), futures()))

    assert catalog.resolve("cost://cn-a-default/v1") == equity()
    assert catalog.resolve("cost://futures-default/v1") == futures()

    with pytest.raises(ValueError):
        catalog.resolve("cost://missing/v1")


def test_catalog_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError):
        InMemoryCostModelCatalog((equity(), equity()))
