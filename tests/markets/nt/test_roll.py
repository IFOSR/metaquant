from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from quant_platform.markets.nt.roll import RollTransition, build_roll_transitions


def test_build_roll_transitions_detects_switch() -> None:
    history = (
        (date(2026, 8, 14), "RB2601"),
        (date(2026, 8, 17), "RB2605"),
    )
    prices = {
        "RB2601": {date(2026, 8, 17): Decimal("4000")},
        "RB2605": {date(2026, 8, 17): Decimal("3900")},
    }

    transitions = build_roll_transitions(history, prices)

    assert len(transitions) == 1
    transition = transitions[0]
    assert transition.from_contract == "RB2601"
    assert transition.to_contract == "RB2605"
    assert transition.from_price == Decimal("4000")
    assert transition.to_price == Decimal("3900")


def test_no_transition_when_same_contract() -> None:
    history = (
        (date(2026, 8, 14), "RB2601"),
        (date(2026, 8, 17), "RB2601"),
    )

    assert build_roll_transitions(history, {}) == ()


def test_skip_missing_price() -> None:
    history = (
        (date(2026, 8, 14), "RB2601"),
        (date(2026, 8, 17), "RB2605"),
    )

    # 缺失换月日的价格 → 跳过，不产出转换
    assert build_roll_transitions(history, {}) == ()


def test_roll_transition_rejects_same_contract() -> None:
    with pytest.raises(ValueError, match="differ"):
        RollTransition(
            transition_date=date(2026, 8, 17),
            from_contract="RB2601",
            to_contract="RB2601",
            from_price=Decimal("4000"),
            to_price=Decimal("3900"),
        )
