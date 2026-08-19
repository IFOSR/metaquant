"""Tests for the factor build spec (build-spec/v1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from quant_platform.factor_construction.spec import (
    FactorBuildSpec,
    LabelSpec,
    build_spec_hash,
)


def make_spec(**overrides: object) -> FactorBuildSpec:
    values: dict[str, object] = {
        "factor_id": "cn_a.stable_alpha_dl",
        "factor_name": "StableAlpha",
        "market": "CN_A",
        "universe_ref": "universe://csi-all-pit/v1",
        "inputs": ["open", "high", "low", "close", "volume", "amount", "vwap"],
        "label": {
            "name": "future_21d_vwap_return",
            "price_field": "vwap",
            "horizon": 21,
            "style_neutralize": ["size", "volatility", "reversal", "liquidity"],
        },
        "architecture": "MLP",
        "style_neutralize": ["size", "volatility", "reversal", "liquidity"],
        "sample_weighting": "INVERSE_SIZE",
        "expected_direction": "POSITIVE",
    }
    values.update(overrides)
    return FactorBuildSpec.model_validate(values)


def test_spec_hash_is_stable_across_key_order() -> None:
    first = make_spec()
    second = FactorBuildSpec.model_validate(
        {
            "expected_direction": "POSITIVE",
            "sample_weighting": "INVERSE_SIZE",
            "style_neutralize": ["size", "volatility", "reversal", "liquidity"],
            "architecture": "MLP",
            "label": {
                "name": "future_21d_vwap_return",
                "price_field": "vwap",
                "horizon": 21,
                "style_neutralize": ["size", "volatility", "reversal", "liquidity"],
            },
            "inputs": ["open", "high", "low", "close", "volume", "amount", "vwap"],
            "universe_ref": "universe://csi-all-pit/v1",
            "market": "CN_A",
            "factor_name": "StableAlpha",
            "factor_id": "cn_a.stable_alpha_dl",
        }
    )
    assert build_spec_hash(first) == build_spec_hash(second)
    assert build_spec_hash(first).startswith("sha256:")
    assert len(build_spec_hash(first)) == len("sha256:") + 64


def test_label_price_field_must_be_in_inputs() -> None:
    with pytest.raises(ValidationError):
        make_spec(
            label={"name": "future_5d_return", "price_field": "vwap", "horizon": 5},
            inputs=["close", "open"],
        )


def test_rejects_unknown_architecture() -> None:
    with pytest.raises(ValidationError):
        make_spec(architecture="GAN")


def test_rejects_unknown_sample_weighting() -> None:
    with pytest.raises(ValidationError):
        make_spec(sample_weighting="WEIRD")


def test_label_spec_parses_from_article_shape() -> None:
    label = LabelSpec.model_validate(
        {"name": "future_21d_vwap_return", "price_field": "vwap", "horizon": 21}
    )
    assert label.style_neutralize == []
    assert label.return_type == "simple"


def test_stable_alpha_spec_captures_article_methodology() -> None:
    spec = make_spec()
    assert spec.label.horizon == 21
    assert spec.label.price_field == "vwap"
    assert set(spec.style_neutralize) == {"size", "volatility", "reversal", "liquidity"}
    assert spec.sample_weighting == "INVERSE_SIZE"
