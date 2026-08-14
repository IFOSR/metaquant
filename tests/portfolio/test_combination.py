from __future__ import annotations

import pytest

from quant_platform.portfolio.combination import (
    CombinationSpec,
    FactorSignal,
    combine,
    equal_weight,
    factor_ablation,
    marginal_contributions,
    mvp_combine,
)
from quant_platform.validation.alpha_pool import FactorDirection


def spec() -> CombinationSpec:
    return CombinationSpec(spec_id="combo://cn-a-mvp/v1")


def signals() -> tuple[FactorSignal, ...]:
    return (
        FactorSignal(
            factor_ir_hash="a" * 64,
            train_ic=0.05,
            ic_vol=0.02,
            direction=FactorDirection.LONG_SHORT,
        ),
        FactorSignal(
            factor_ir_hash="b" * 64,
            train_ic=0.02,
            ic_vol=0.02,
            direction=FactorDirection.LONG_SHORT,
        ),
        FactorSignal(
            factor_ir_hash="c" * 64,
            train_ic=-0.01,
            ic_vol=0.02,
            direction=FactorDirection.LONG_SHORT,
        ),
    )


def test_equal_weight_baseline_sums_to_one() -> None:
    weights = equal_weight(signals(), spec())

    assert weights.method == "equal_weight"
    assert all(weight == pytest.approx(1.0 / 3.0) for _, weight in weights.entries)


def test_mvp_combine_sums_to_one() -> None:
    weights = mvp_combine(signals(), spec())

    total = sum(weight for _, weight in weights.entries)
    assert total == pytest.approx(1.0)


def test_mvp_combine_credits_stronger_ic() -> None:
    weights = mvp_combine(signals(), spec())
    weight_map = weights.weights_map()

    # factor a has the largest |IC|, so it should receive the largest weight
    assert weight_map["a" * 64] > weight_map["b" * 64]
    assert weight_map["b" * 64] > weight_map["c" * 64]


def test_full_shrinkage_is_equal_weight() -> None:
    full_shrink = CombinationSpec(spec_id="combo://full/v1", shrinkage=1.0)
    weights = mvp_combine(signals(), full_shrink)

    for _, weight in weights.entries:
        assert weight == pytest.approx(1.0 / 3.0)


def test_long_only_ignores_negative_ic() -> None:
    signals_only = (
        FactorSignal(
            factor_ir_hash="a" * 64,
            train_ic=0.05,
            ic_vol=0.02,
            direction=FactorDirection.LONG_SHORT,
        ),
        FactorSignal(
            factor_ir_hash="b" * 64,
            train_ic=-0.05,
            ic_vol=0.02,
            direction=FactorDirection.LONG_ONLY,
        ),
    )
    weights = mvp_combine(
        signals_only, CombinationSpec(spec_id="s", shrinkage=0.0, max_weight=1.0)
    )
    weight_map = weights.weights_map()

    # long-only factor with negative IC has zero strength, so zero weight
    assert weight_map["b" * 64] == pytest.approx(0.0)
    assert weight_map["a" * 64] == pytest.approx(1.0)


def test_short_only_credits_negative_ic() -> None:
    signal = FactorSignal(
        factor_ir_hash="a" * 64,
        train_ic=-0.05,
        ic_vol=0.02,
        direction=FactorDirection.SHORT_ONLY,
    )

    assert signal.directional_ic() == pytest.approx(0.05)
    assert signal.strength() == pytest.approx(0.05 / 0.02)


def test_max_weight_bound_is_enforced() -> None:
    capped = CombinationSpec(spec_id="s", shrinkage=0.0, max_weight=0.5)
    weights = mvp_combine(signals(), capped)

    for _, weight in weights.entries:
        assert weight <= 0.5 + 1e-9


def test_rejects_empty_signals() -> None:
    with pytest.raises(ValueError):
        mvp_combine((), spec())


def test_max_weight_relaxes_when_tighter_than_equal_weight() -> None:
    impossible = CombinationSpec(spec_id="s", max_weight=0.2)
    weights = mvp_combine(signals(), impossible)

    # cap of 0.2 is infeasible with 3 factors summing to one, so it relaxes to
    # the equal-weight point 1/3
    for _, weight in weights.entries:
        assert weight == pytest.approx(1.0 / 3.0)


def test_rejects_bad_hash() -> None:
    with pytest.raises(ValueError):
        FactorSignal(
            factor_ir_hash="not-a-hash",
            train_ic=0.05,
            ic_vol=0.02,
        )


def test_rejects_nonpositive_ic_vol() -> None:
    with pytest.raises(ValueError):
        FactorSignal(factor_ir_hash="a" * 64, train_ic=0.05, ic_vol=0.0)


def test_ablation_reports_delta() -> None:
    ablations = factor_ablation(signals(), spec())

    assert len(ablations) == 3
    # dropping the strongest factor reduces expected IC the most
    strongest = ablations[0]
    assert strongest.factor_ir_hash == "a" * 64
    assert strongest.delta > 0.0


def test_marginal_contributions_sum_to_one() -> None:
    weights = mvp_combine(signals(), spec())
    contributions = marginal_contributions(signals(), weights)

    total = sum(value for _, value in contributions)
    assert total == pytest.approx(1.0)


def test_combine_report_is_deterministic() -> None:
    first = combine(signals(), spec())
    second = combine(signals(), spec())

    assert first == second
    assert first.content_hash() == second.content_hash()


def test_combine_report_shape() -> None:
    report = combine(signals(), spec())

    assert report.weights.method == "ic_weighted"
    assert report.equal_weight.method == "equal_weight"
    assert len(report.ablations) == 3
    assert len(report.marginal_contributions) == 3
    assert report.expected_ic >= 0.0
