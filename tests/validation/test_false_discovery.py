from __future__ import annotations

import pytest

from quant_platform.validation.false_discovery import (
    FalseDiscoveryReport,
    run_false_discovery,
)


def strategy_returns() -> tuple[tuple[float, ...], ...]:
    return (
        tuple(float(index) for index in range(1, 17)),
        tuple(float(16 - index) for index in range(16)),
    )


def test_run_false_discovery_is_deterministic() -> None:
    p_values = (0.01, 0.02, 0.5)

    first = run_false_discovery(p_values, strategy_returns())
    second = run_false_discovery(p_values, strategy_returns())

    assert first == second
    assert first.content_hash() == second.content_hash()


def test_bh_adjustment_and_rejection_count() -> None:
    p_values = (0.01, 0.02, 0.5)

    report = run_false_discovery(p_values, strategy_returns())

    assert report.adjusted_pvalues == pytest.approx((0.03, 0.03, 0.5))
    assert report.rejected_count == 2
    assert report.candidate_count == 3


def test_deflated_sharpe_ratio_is_computed_when_moments_given() -> None:
    p_values = (0.01, 0.02, 0.5)

    report = run_false_discovery(
        p_values,
        strategy_returns(),
        sharpe=1.5,
        skew=-0.2,
        kurtosis=3.5,
        n_observations=252,
    )

    assert report.deflated_sharpe_ratio is not None
    assert 0.0 <= report.deflated_sharpe_ratio <= 1.0


def test_dsr_and_pbo_are_none_without_inputs() -> None:
    p_values = (0.01,)

    report = run_false_discovery(p_values, ())

    assert report.deflated_sharpe_ratio is None
    assert report.pbo is None  # fewer than two strategies


def test_rejects_invalid_p_values() -> None:
    with pytest.raises(ValueError):
        run_false_discovery((0.01, 1.5), strategy_returns())


def test_rejects_empty_p_values() -> None:
    with pytest.raises(ValueError):
        run_false_discovery((), strategy_returns())


def test_report_has_expected_schema() -> None:
    report = run_false_discovery((0.01, 0.02), strategy_returns())

    assert isinstance(report, FalseDiscoveryReport)
    assert report.payload()["schema_version"] == "false-discovery/v1"
