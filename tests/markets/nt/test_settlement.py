from __future__ import annotations

from decimal import Decimal

from quant_platform.markets.nt.settlement import SettlementLeg, settle_daily


def test_settle_daily_mark_to_market() -> None:
    result = settle_daily(
        (
            SettlementLeg(
                instrument_id="RB2610.SHF",
                previous_quantity=1,
                previous_settlement=Decimal("4000"),
                opened_quantity=0,
                opened_price=Decimal("4000"),
                settlement_price=Decimal("4010"),
            ),
        ),
        multiplier=Decimal("10"),
    )

    # 多头：结算价 4010 vs 昨结 4000，10 元/吨 × 10 乘数 × 1 手 = 100
    assert result.mark_to_market == Decimal("100")
    assert result.ending_quantities == {"RB2610.SHF": 1}


def test_settle_daily_aggregates_multiple_legs() -> None:
    result = settle_daily(
        (
            SettlementLeg(
                instrument_id="RB2610.SHF",
                previous_quantity=1,
                previous_settlement=Decimal("4000"),
                opened_quantity=0,
                opened_price=Decimal("4000"),
                settlement_price=Decimal("4010"),
            ),
            SettlementLeg(
                instrument_id="AU2612.SHF",
                previous_quantity=2,
                previous_settlement=Decimal("950"),
                opened_quantity=0,
                opened_price=Decimal("950"),
                settlement_price=Decimal("945"),
            ),
        ),
        multiplier=Decimal("10"),
    )

    # RB: +100；AU: (945-950)*10*2 = -100；合计 0
    assert result.mark_to_market == Decimal("0")


def test_settle_daily_deducts_fees() -> None:
    result = settle_daily(
        (
            SettlementLeg(
                instrument_id="RB2610.SHF",
                previous_quantity=1,
                previous_settlement=Decimal("4000"),
                opened_quantity=0,
                opened_price=Decimal("4000"),
                settlement_price=Decimal("4010"),
            ),
        ),
        multiplier=Decimal("10"),
        fees=Decimal("30"),
    )

    assert result.mark_to_market == Decimal("70")
