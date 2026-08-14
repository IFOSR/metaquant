from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.validation.alpha_pool import FactorDirection
from quant_platform.validation.combination_pool import (
    CombinationPool,
    PromotedFactor,
)


def promoted(prefix: str) -> PromotedFactor:
    return PromotedFactor(
        factor_ir_hash=prefix * 64,
        market="CN_A",
        direction=FactorDirection.LONG_SHORT,
        promotion_evidence_hash="e" * 64,
        promoted_at=datetime(2026, 8, 14, tzinfo=UTC),
    )


def test_add_and_contains() -> None:
    pool = CombinationPool(()).add(promoted("a"))

    assert pool.contains("a" * 64) is True
    assert pool.contains("b" * 64) is False


def test_add_duplicate_fails_closed() -> None:
    pool = CombinationPool(()).add(promoted("a"))

    with pytest.raises(ValueError):
        pool.add(promoted("a"))


def test_resolve_missing_fails_closed() -> None:
    pool = CombinationPool(()).add(promoted("a"))

    with pytest.raises(ValueError):
        pool.resolve("b" * 64)


def test_rejects_duplicate_hash_at_construction() -> None:
    with pytest.raises(ValueError):
        CombinationPool((promoted("a"), promoted("a")))


def test_rejects_invalid_hash() -> None:
    with pytest.raises(ValueError):
        PromotedFactor(
            factor_ir_hash="not-a-hash",
            market="CN_A",
            direction=FactorDirection.LONG_SHORT,
            promotion_evidence_hash="e" * 64,
            promoted_at=datetime(2026, 8, 14, tzinfo=UTC),
        )


def test_pool_is_deterministic() -> None:
    pool = CombinationPool((promoted("a"), promoted("b")))

    assert pool.payload() == pool.payload()
    assert pool.content_hash() == pool.content_hash()
