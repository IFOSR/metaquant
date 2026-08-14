from __future__ import annotations

from decimal import Decimal

import pytest

from quant_platform.strategy.package import (
    DataManifest,
    build_package,
    verify_package,
)
from quant_platform.strategy.spec import RiskLimits, StrategySpec

D = Decimal


def spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="strategy://cn-a-momentum/v1",
        market="CN_A",
        universe_ref="universe://csi300-pit/v1",
        frequency="1d",
        factor_weights=(("a" * 64, D("0.5")), ("b" * 64, D("0.5"))),
        leverage=D("1"),
        risk_limits=RiskLimits(
            max_single_weight=D("0.1"),
            max_holdings=50,
            turnover_budget=D("0.3"),
        ),
        cost_model_ref="cost://cn-a-default/v1",
        validation_policy_ref="policy://cn-a-daily-factor/v1",
    )


def manifest() -> DataManifest:
    return DataManifest(
        snapshot_id="snapshot-cn-a-001",
        snapshot_manifest_hash="1" * 64,
        rule_version="cn-a-rules/2026-08",
        code_version="quant-platform/0.1.0",
        dependency_lock_hash="2" * 64,
    )


def test_spec_content_hash_is_stable() -> None:
    assert spec().content_hash() == spec().content_hash()


def test_spec_rejects_non_unit_weights() -> None:
    with pytest.raises(ValueError):
        StrategySpec(
            strategy_id="s",
            market="CN_A",
            universe_ref="u",
            frequency="1d",
            factor_weights=(("a" * 64, D("0.3")), ("b" * 64, D("0.3"))),
            leverage=D("1"),
            risk_limits=RiskLimits(D("0.1"), 50, D("0.3")),
            cost_model_ref="c",
            validation_policy_ref="p",
        )


def test_spec_rejects_duplicate_factor() -> None:
    with pytest.raises(ValueError):
        StrategySpec(
            strategy_id="s",
            market="CN_A",
            universe_ref="u",
            frequency="1d",
            factor_weights=(("a" * 64, D("0.5")), ("a" * 64, D("0.5"))),
            leverage=D("1"),
            risk_limits=RiskLimits(D("0.1"), 50, D("0.3")),
            cost_model_ref="c",
            validation_policy_ref="p",
        )


def test_spec_requires_roll_policy_for_futures() -> None:
    with pytest.raises(ValueError):
        StrategySpec(
            strategy_id="s",
            market="CN_COMMODITY_FUTURES",
            universe_ref="u",
            frequency="1d",
            factor_weights=(("a" * 64, D("1.0")),),
            leverage=D("1"),
            risk_limits=RiskLimits(D("0.1"), 50, D("0.3")),
            cost_model_ref="c",
            validation_policy_ref="p",
        )


def test_package_content_hash_is_stable() -> None:
    first = build_package(
        package_id="pkg://strategy/v1",
        spec=spec(),
        data_manifest=manifest(),
        backtest_result_hash="3" * 64,
    )
    second = build_package(
        package_id="pkg://strategy/v1",
        spec=spec(),
        data_manifest=manifest(),
        backtest_result_hash="3" * 64,
    )

    assert first.content_hash() == second.content_hash()


def test_package_sign_and_verify() -> None:
    package = build_package(
        package_id="pkg://strategy/v1",
        spec=spec(),
        data_manifest=manifest(),
        backtest_result_hash="3" * 64,
    )

    signed = package.sign(b"secret-key")
    assert signed.verify(b"secret-key")


def test_package_verify_fails_with_wrong_key() -> None:
    package = build_package(
        package_id="pkg://strategy/v1",
        spec=spec(),
        data_manifest=manifest(),
        backtest_result_hash="3" * 64,
    ).sign(b"secret-key")

    assert not package.verify(b"other-key")


def test_package_content_hash_excludes_signature() -> None:
    unsigned = build_package(
        package_id="pkg://strategy/v1",
        spec=spec(),
        data_manifest=manifest(),
        backtest_result_hash="3" * 64,
    )
    signed = unsigned.sign(b"secret-key")

    assert signed.content_hash() == unsigned.content_hash()


def test_unsigned_package_verify_fails() -> None:
    package = build_package(
        package_id="pkg://strategy/v1",
        spec=spec(),
        data_manifest=manifest(),
        backtest_result_hash="3" * 64,
    )

    assert not package.verify(b"secret-key")
    assert not verify_package(package, b"secret-key")


def test_rejects_empty_signing_key() -> None:
    package = build_package(
        package_id="pkg://strategy/v1",
        spec=spec(),
        data_manifest=manifest(),
        backtest_result_hash="3" * 64,
    )

    with pytest.raises(ValueError):
        package.sign(b"")
