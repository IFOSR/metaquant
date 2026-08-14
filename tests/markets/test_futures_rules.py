from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import pytest

from quant_platform.markets.clocks import (
    AsiaShanghaiClock,
    CommodityFuturesClock,
    FuturesSessionTemplate,
)
from quant_platform.markets.contracts import MarketId
from quant_platform.markets.cost import FuturesCostModel
from quant_platform.markets.futures import (
    CloseOffset,
    DeliveryPolicy,
    FeeRate,
    FeeSchedule,
    FuturesPosition,
    MarginSchedule,
    OpenInterestObservation,
    SettlementInput,
    select_main_contract,
    settle,
)

from .conftest import GOLDEN_ROOT, load_golden_cases, sha256_file


def test_futures_golden_fixture_hash_is_frozen(
    golden_manifest: dict[str, str],
) -> None:
    path = GOLDEN_ROOT / "cn_commodity_futures.json"
    assert sha256_file(path) == golden_manifest["cn_commodity_futures.json"]


@pytest.mark.parametrize(
    "case",
    load_golden_cases("cn_commodity_futures"),
    ids=lambda case: case["id"],
)
def test_futures_representative_golden_cases(case: dict[str, object]) -> None:
    inputs = case["inputs"]
    expected = case["expected"]
    assert isinstance(inputs, dict)
    assert isinstance(expected, dict)

    if case["kind"] == "settlement":
        settlement_result = settle(
            SettlementInput(
                previous_quantity=int(inputs["previous_quantity"]),
                previous_settlement=Decimal(inputs["previous_settlement"]),
                opened_quantity=int(inputs["opened_quantity"]),
                opened_price=Decimal(inputs["opened_price"]),
                settlement_price=Decimal(inputs["settlement_price"]),
                multiplier=Decimal(inputs["multiplier"]),
                fees=Decimal(inputs["fees"]),
            )
        )
        assert {
            "mark_to_market": str(settlement_result.mark_to_market),
            "ending_quantity": settlement_result.ending_quantity,
        } == expected
    elif case["kind"] == "margin":
        margin = MarginSchedule(
            exchange_rate=Decimal(inputs["exchange_rate"]),
            broker_rate=Decimal(inputs["broker_rate"]),
        ).required_margin(
            settlement_price=Decimal(inputs["settlement_price"]),
            multiplier=Decimal(inputs["multiplier"]),
            quantity=int(inputs["quantity"]),
        )
        assert str(margin) == expected["required_margin"]
    elif case["kind"] == "fee":
        schedule = FeeSchedule(
            {
                CloseOffset.CLOSE_TODAY: FeeRate(
                    per_lot=Decimal(inputs["close_today_per_lot"])
                ),
                CloseOffset.CLOSE_YESTERDAY: FeeRate(
                    per_lot=Decimal(inputs["close_yesterday_per_lot"])
                ),
            }
        )
        assert (
            str(
                schedule.calculate(
                    CloseOffset(inputs["offset"]),
                    quantity=int(inputs["quantity"]),
                    price=Decimal(inputs["price"]),
                    multiplier=Decimal(inputs["multiplier"]),
                )
            )
            == expected["fee"]
        )
    elif case["kind"] == "close_offset":
        position = FuturesPosition(
            today_quantity=int(inputs["today_quantity"]),
            yesterday_quantity=int(inputs["yesterday_quantity"]),
        )
        position_result = position.close(
            int(inputs["quantity"]),
            CloseOffset(inputs["offset"]),
        )
        assert {
            "today_quantity": position_result.today_quantity,
            "yesterday_quantity": position_result.yesterday_quantity,
        } == expected
    elif case["kind"] == "delivery_exit":
        policy = DeliveryPolicy(
            force_exit_date=date.fromisoformat(inputs["force_exit_date"]),
            delivery_allowed=False,
        )
        assert (
            policy.may_open(date.fromisoformat(inputs["as_of"]))
            is (expected["may_open"])
        )
        assert (
            policy.must_exit(date.fromisoformat(inputs["as_of"]))
            is (expected["must_exit"])
        )
    elif case["kind"] == "main_contract":
        observations = tuple(
            OpenInterestObservation(
                trade_date=date.fromisoformat(row["trade_date"]),
                contract=row["contract"],
                delivery_month=int(row["delivery_month"]),
                open_interest=Decimal(row["open_interest"]),
            )
            for row in inputs["observations"]
        )
        selected = select_main_contract(
            current_contract=inputs["current_contract"],
            decision_date=date.fromisoformat(inputs["decision_date"]),
            observations=observations,
            confirmation_days=int(inputs["confirmation_days"]),
            threshold=Decimal(inputs["threshold"]),
        )
        assert selected == expected["contract"]
    elif case["kind"] == "night_trade_date":
        clock = CommodityFuturesClock(
            FuturesSessionTemplate(
                product=str(inputs["product"]),
                night_start=time.fromisoformat(str(inputs["night_start"])),
                night_end=time.fromisoformat(str(inputs["night_end"])),
                settlement_at=time.fromisoformat(str(inputs["settlement_at"])),
            ),
            night_trade_dates={
                date.fromisoformat(str(inputs["night_calendar_date"])): (
                    date.fromisoformat(str(inputs["exchange_trade_date"]))
                )
            },
            trading_dates=frozenset(
                {date.fromisoformat(str(inputs["exchange_trade_date"]))}
            ),
        )
        timestamp = datetime.fromisoformat(str(inputs["timestamp"]))
        assert (
            clock.trade_date(AsiaShanghaiClock.localize(timestamp)).isoformat()
            == (expected["trade_date"])
        )
    elif case["kind"] == "transaction_cost":
        model = FuturesCostModel(
            model_id="cost://golden/v1",
            market=MarketId.CN_COMMODITY_FUTURES,
            fee_rate=float(inputs["fee_rate"]),
            slippage_bps=0.0,
            impact_bps_per_adv=0.0,
            margin_rate=0.1,
            funding_rate_daily=0.0,
        )
        notional = (
            Decimal(str(inputs["price"]))
            * int(inputs["quantity"])
            * Decimal(str(inputs["multiplier"]))
        )
        single = Decimal(str(model.single_side_cost(float(notional))))
        assert single == Decimal(str(expected["single_side_fee"]))
        round_trip = Decimal(str(model.round_trip_cost(float(notional))))
        assert round_trip == Decimal(str(expected["round_trip_fee"]))
    else:
        raise AssertionError(f"unsupported golden case kind: {case['kind']}")


def test_broker_margin_may_not_be_below_exchange_minimum() -> None:
    with pytest.raises(ValueError, match="exchange minimum"):
        MarginSchedule(
            exchange_rate=Decimal("0.12"),
            broker_rate=Decimal("0.10"),
        )


def test_close_offset_cannot_consume_the_wrong_lot_bucket() -> None:
    position = FuturesPosition(today_quantity=3, yesterday_quantity=1)

    with pytest.raises(ValueError, match="yesterday"):
        position.close(2, CloseOffset.CLOSE_YESTERDAY)


def test_main_contract_selection_is_unchanged_when_future_rows_are_removed() -> None:
    observations = tuple(
        OpenInterestObservation(
            trade_date=date(2026, 8, day),
            contract=contract,
            delivery_month=delivery_month,
            open_interest=Decimal(open_interest),
        )
        for day, contract, delivery_month, open_interest in [
            (7, "RB2610", 202610, "100"),
            (7, "RB2701", 202701, "125"),
            (8, "RB2610", 202610, "100"),
            (8, "RB2701", 202701, "125"),
            (9, "RB2610", 202610, "100"),
            (9, "RB2701", 202701, "125"),
            (10, "RB2610", 202610, "100"),
            (10, "RB2701", 202701, "10"),
        ]
    )

    full = select_main_contract(
        "RB2610",
        date(2026, 8, 9),
        observations,
        confirmation_days=3,
        threshold=Decimal("1.2"),
    )
    truncated = select_main_contract(
        "RB2610",
        date(2026, 8, 9),
        tuple(item for item in observations if item.trade_date <= date(2026, 8, 9)),
        confirmation_days=3,
        threshold=Decimal("1.2"),
    )

    assert full == truncated == "RB2701"
