from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from quant_platform.markets.cn_a import (
    AShareDailyState,
    ASharePosition,
    CashDividend,
    CorporateActionLedger,
    FillCertainty,
    MembershipEvent,
    OrderSide,
    PositionLot,
    PriceLimitRule,
    SecurityStatus,
    SecurityStatusEvent,
    SplitAction,
    membership_as_of,
    security_status_as_of,
)

from .conftest import GOLDEN_ROOT, load_golden_cases, sha256_file


def test_cn_a_golden_fixture_hash_is_frozen(
    golden_manifest: dict[str, str],
) -> None:
    path = GOLDEN_ROOT / "cn_a.json"
    assert sha256_file(path) == golden_manifest["cn_a.json"]


@pytest.mark.parametrize(
    "case",
    load_golden_cases("cn_a"),
    ids=lambda case: case["id"],
)
def test_cn_a_representative_golden_cases(case: dict[str, object]) -> None:
    inputs = case["inputs"]
    expected = case["expected"]
    assert isinstance(inputs, dict)
    assert isinstance(expected, dict)

    if case["kind"] == "t_plus_one":
        position = ASharePosition(
            tuple(
                PositionLot(
                    quantity=int(lot["quantity"]),
                    acquired_on=date.fromisoformat(str(lot["acquired_on"])),
                )
                for lot in inputs["lots"]
            )
        )
        assert (
            position.sellable_quantity(date.fromisoformat(inputs["trade_date"]))
            == (expected["sellable_quantity"])
        )
    elif case["kind"] == "price_limit":
        lower, upper = PriceLimitRule(
            percentage=Decimal(inputs["percentage"]),
            tick_size=Decimal(inputs["tick_size"]),
        ).band(Decimal(inputs["basis_price"]))
        assert {"lower": str(lower), "upper": str(upper)} == expected
    elif case["kind"] == "tradability":
        assessment = AShareDailyState(
            halted=inputs["halted"],
            volume=int(inputs["volume"]),
            high=Decimal(inputs["high"]),
            low=Decimal(inputs["low"]),
            upper_limit=Decimal(inputs["upper_limit"]),
            lower_limit=Decimal(inputs["lower_limit"]),
        ).assess(OrderSide(inputs["side"]))
        assert {
            "certainty": assessment.certainty.value,
            "reason": assessment.reason,
        } == expected
    elif case["kind"] == "status":
        status_event = SecurityStatusEvent(
            status=SecurityStatus(inputs["status"]),
            announced_at=datetime.fromisoformat(inputs["announced_at"]),
            effective_from=date.fromisoformat(inputs["effective_from"]),
        )
        status = security_status_as_of(
            (status_event,),
            date.fromisoformat(inputs["trade_date"]),
            datetime.fromisoformat(inputs["decision_at"]),
        )
        assert status.value == expected["status"]
    elif case["kind"] == "membership":
        membership_event = MembershipEvent(
            index_id=inputs["index_id"],
            instrument_id=inputs["instrument_id"],
            announced_at=datetime.fromisoformat(inputs["announced_at"]),
            effective_from=date.fromisoformat(inputs["effective_from"]),
            effective_to=None,
        )
        assert (
            membership_as_of(
                (membership_event,),
                inputs["index_id"],
                inputs["instrument_id"],
                date.fromisoformat(inputs["trade_date"]),
                datetime.fromisoformat(inputs["decision_at"]),
            )
            is expected["included"]
        )
    elif case["kind"] == "corporate_action":
        ledger = CorporateActionLedger(
            quantity=int(inputs["quantity"]),
            cash=Decimal(inputs["cash"]),
            cost_basis_per_share=Decimal(inputs["cost_basis_per_share"]),
        )
        corporate_action: CashDividend | SplitAction
        if inputs["action"] == "cash_dividend":
            corporate_action = CashDividend(
                record_date=date.fromisoformat(inputs["record_date"]),
                ex_date=date.fromisoformat(inputs["ex_date"]),
                payable_date=date.fromisoformat(inputs["payable_date"]),
                cash_per_share=Decimal(inputs["cash_per_share"]),
            )
        else:
            corporate_action = SplitAction(
                record_date=date.fromisoformat(inputs["record_date"]),
                ex_date=date.fromisoformat(inputs["ex_date"]),
                ratio=Decimal(inputs["ratio"]),
            )
        result = ledger.apply(
            corporate_action,
            date.fromisoformat(inputs["as_of"]),
        )
        assert {
            "quantity": result.quantity,
            "cash": str(result.cash),
            "cost_basis_per_share": str(result.cost_basis_per_share),
        } == expected
    else:
        raise AssertionError(f"unsupported golden case kind: {case['kind']}")


def test_intraday_evidence_can_mark_an_opened_limit_as_eligible() -> None:
    state = AShareDailyState(
        halted=False,
        volume=1000,
        high=Decimal("11.00"),
        low=Decimal("10.50"),
        upper_limit=Decimal("11.00"),
        lower_limit=Decimal("9.00"),
        intraday_limit_opened=True,
    )

    assert state.assess(OrderSide.BUY).certainty is FillCertainty.ELIGIBLE


def test_position_rejects_sale_above_t_plus_one_sellable_quantity() -> None:
    position = ASharePosition(
        (
            PositionLot(100, date(2026, 8, 10)),
            PositionLot(100, date(2026, 8, 11)),
        )
    )

    with pytest.raises(ValueError, match="T\\+1"):
        position.sell(101, date(2026, 8, 11))


def test_status_event_is_not_visible_before_announcement() -> None:
    event = SecurityStatusEvent(
        status=SecurityStatus.ST,
        announced_at=datetime(2026, 8, 10, 10, tzinfo=UTC),
        effective_from=date(2026, 8, 11),
    )

    assert (
        security_status_as_of(
            (event,),
            date(2026, 8, 11),
            datetime(2026, 8, 10, 9, tzinfo=UTC),
        )
        is SecurityStatus.NORMAL
    )
