from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.validation import (
    ForwardReturnLabel,
    LabelObservation,
    LabelSeries,
    assert_label_pit_safe,
)


def at(day: int) -> datetime:
    return datetime(2026, 8, day, 15, tzinfo=UTC)


def label() -> ForwardReturnLabel:
    return ForwardReturnLabel(
        label_id="label.cn_a.forward_5d",
        market="CN_A",
        horizon=5,
        field_ref="market.eod.forward_return_5d",
    )


def test_forward_return_label_rejects_invalid_horizon() -> None:
    with pytest.raises(ValueError, match="horizon"):
        ForwardReturnLabel(
            label_id="label-001",
            market="CN_A",
            horizon=7,
            field_ref="market.eod.forward_return_5d",
        )


def test_forward_return_label_rejects_invalid_market() -> None:
    with pytest.raises(ValueError, match="market"):
        ForwardReturnLabel(
            label_id="label-001",
            market="US",
            horizon=5,
            field_ref="market.eod.forward_return_5d",
        )


def test_forward_return_label_rejects_unknown_return_definition() -> None:
    with pytest.raises(ValueError, match="return_definition"):
        ForwardReturnLabel(
            label_id="label-001",
            market="CN_A",
            horizon=5,
            field_ref="market.eod.forward_return_5d",
            return_definition="open_to_open",
        )


def test_label_observation_rejects_non_finite_value() -> None:
    with pytest.raises(ValueError, match="finite"):
        LabelObservation("600000.SSE", at(1), float("inf"))


def test_label_series_requires_unique_observations() -> None:
    with pytest.raises(ValueError, match="unique"):
        LabelSeries(
            label=label(),
            observations=(
                LabelObservation("600000.SSE", at(1), 0.01),
                LabelObservation("600000.SSE", at(1), 0.02),
            ),
        )


def test_label_series_content_hash_is_stable() -> None:
    series = LabelSeries(
        label=label(),
        observations=(LabelObservation("600000.SSE", at(1), 0.01),),
    )

    assert len(series.content_hash()) == 64
    assert series.content_hash() == series.content_hash()


def test_label_pit_safe_requires_available_after_decision() -> None:
    assert_label_pit_safe(
        label_available_time=at(12),
        decision_time=at(5),
    )

    with pytest.raises(ValueError, match="strictly after"):
        assert_label_pit_safe(
            label_available_time=at(5),
            decision_time=at(5),
        )
