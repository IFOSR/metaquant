from __future__ import annotations

from typing import cast

import pytest

from quant_platform.validation.alpha_pool import (
    AlphaPool,
    AlphaPoolFactor,
    FactorDirection,
    InMemoryAlphaPoolCatalog,
    LifecycleState,
)


def _factor(ir_hash: str = "a" * 64) -> AlphaPoolFactor:
    return AlphaPoolFactor(
        factor_ir_hash=ir_hash,
        direction=FactorDirection.LONG_SHORT,
        market="CN_A",
        universe="cn-a-001",
        horizon=5,
        policy_id="policy://cn-a-daily-factor/v1",
        risk_premium=False,
        lifecycle_state=LifecycleState.CANDIDATE,
    )


def test_constructs_and_hashes_deterministically() -> None:
    first = _factor()
    second = _factor()

    assert first == second
    assert first.content_hash() == second.content_hash()
    assert len(first.content_hash()) == 64


def test_rejects_invalid_ir_hash() -> None:
    with pytest.raises(ValueError):
        _factor(ir_hash="not-hex")


def test_rejects_invalid_market() -> None:
    with pytest.raises(ValueError):
        AlphaPoolFactor(
            factor_ir_hash="a" * 64,
            direction=FactorDirection.LONG_SHORT,
            market="NYSE",
            universe="cn-a-001",
            horizon=5,
            policy_id="policy://cn-a-daily-factor/v1",
            risk_premium=False,
            lifecycle_state=LifecycleState.CANDIDATE,
        )


def test_rejects_non_positive_horizon() -> None:
    with pytest.raises(ValueError):
        AlphaPoolFactor(
            factor_ir_hash="a" * 64,
            direction=FactorDirection.LONG_SHORT,
            market="CN_A",
            universe="cn-a-001",
            horizon=0,
            policy_id="policy://cn-a-daily-factor/v1",
            risk_premium=False,
            lifecycle_state=LifecycleState.CANDIDATE,
        )


def test_alpha_pool_rejects_duplicate_ir_hash() -> None:
    with pytest.raises(ValueError):
        AlphaPool((_factor("a" * 64), _factor("a" * 64)))


def test_alpha_pool_resolves_by_ir_hash_and_fails_closed() -> None:
    pool = AlphaPool((_factor("a" * 64), _factor("b" * 64)))

    assert pool.resolve("a" * 64).factor_ir_hash == "a" * 64
    assert pool.ir_hashes() == frozenset({"a" * 64, "b" * 64})
    with pytest.raises(ValueError):
        pool.resolve("c" * 64)


def test_alpha_pool_payload_round_trips() -> None:
    pool = AlphaPool((_factor("a" * 64),))
    payload = pool.payload()

    factors = cast(list[dict[str, object]], payload["factors"])
    assert payload["schema_version"] == "alpha-pool/v1"
    assert len(factors) == 1
    assert factors[0]["factor_ir_hash"] == "a" * 64


def test_catalog_returns_pool() -> None:
    pool = AlphaPool((_factor("a" * 64),))
    catalog = InMemoryAlphaPoolCatalog(pool)

    assert catalog.resolve() == pool
