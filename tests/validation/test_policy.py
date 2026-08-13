from __future__ import annotations

from typing import Any, cast

import pytest

from quant_platform.validation import (
    ICSign,
    InMemoryValidationPolicyCatalog,
    ValidationPolicy,
)


def policy(**changes: object) -> ValidationPolicy:
    values: dict[str, object] = {
        "policy_id": "policy://cn-a-daily-factor/v1",
        "market": "CN_A",
        "min_coverage": 0.8,
        "min_observations": 120,
        "max_constant_ratio": 0.9,
        "ic_sign": ICSign.ANY,
        "min_icir": 0.3,
        "min_nw_t": 2.0,
        "quantile_count": 5,
        "decay_horizons": (1, 5, 10, 20, 60),
    }
    values.update(changes)
    return ValidationPolicy(**cast(Any, values))


def test_policy_rejects_invalid_coverage() -> None:
    with pytest.raises(ValueError, match="min_coverage"):
        policy(min_coverage=1.5)


def test_policy_rejects_invalid_quantile_count() -> None:
    with pytest.raises(ValueError, match="quantile_count"):
        policy(quantile_count=1)


def test_policy_rejects_invalid_decay_horizon() -> None:
    with pytest.raises(ValueError, match="decay_horizons"):
        policy(decay_horizons=(1, 7))


def test_policy_rejects_duplicate_decay_horizons() -> None:
    with pytest.raises(ValueError, match="unique"):
        policy(decay_horizons=(5, 5))


def test_policy_accepts_string_ic_sign() -> None:
    parsed = policy(ic_sign="POSITIVE")
    assert parsed.ic_sign is ICSign.POSITIVE


def test_policy_content_hash_is_stable() -> None:
    assert len(policy().content_hash()) == 64
    assert policy().content_hash() == policy().content_hash()


def test_catalog_resolves_policy_and_fails_closed() -> None:
    catalog = InMemoryValidationPolicyCatalog(
        (policy(), policy(policy_id="policy://cn-a-daily-factor/v2"))
    )

    assert catalog.resolve("policy://cn-a-daily-factor/v1") is not None

    with pytest.raises(ValueError, match="VALIDATION_POLICY_NOT_REGISTERED"):
        catalog.resolve("policy://missing/v1")


def test_catalog_rejects_duplicate_policy_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        InMemoryValidationPolicyCatalog((policy(), policy()))
