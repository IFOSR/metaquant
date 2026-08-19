"""Tests for agent-driven build spec extraction and code generation (mocked)."""

from __future__ import annotations

import json

import pytest

from quant_platform.factor_construction.artifacts import (
    bundle_hash,
    validate_bundle_contract,
)
from quant_platform.factor_construction.generator import (
    _parse_code_files,
    extract_build_spec,
    generate_code_bundle,
)
from quant_platform.factor_construction.spec import build_spec_hash

_SPEC_JSON = {
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

_CODE_OUTPUT = """# file: model.py
```python
def build_model(hyperparams: dict):
    import torch
    return torch.nn.Linear(hyperparams.get("input_dim", 7), 1)
```

# file: train.py
```python
def train(data, spec: dict):
    return build_model(spec["hyperparameters"])
```

# file: infer.py
```python
def infer(data, weights):
    return data.data.values
```
"""


def _spec_ok(_prompt: str) -> str:
    return json.dumps(_SPEC_JSON, ensure_ascii=False)


def _code_ok(_prompt: str) -> str:
    return _CODE_OUTPUT


def test_extract_build_spec_captures_stable_alpha_methodology() -> None:
    spec = extract_build_spec("some report text", runner=_spec_ok)
    assert spec.label.name == "future_21d_vwap_return"
    assert spec.label.horizon == 21
    assert spec.label.price_field == "vwap"
    assert set(spec.style_neutralize) == {"size", "volatility", "reversal", "liquidity"}
    assert spec.sample_weighting.value == "INVERSE_SIZE"


def test_extract_build_spec_retries_on_invalid_json() -> None:
    calls: list[str] = []

    def flaky(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return '{"not": "a spec"}'
        return json.dumps(_SPEC_JSON, ensure_ascii=False)

    spec = extract_build_spec("report", runner=flaky)
    assert spec.factor_id == "cn_a.stable_alpha_dl"
    assert len(calls) == 2


def test_parse_code_files_returns_three_bytes() -> None:
    files = _parse_code_files(_CODE_OUTPUT)
    assert set(files) == {"model.py", "train.py", "infer.py"}
    assert b"def build_model" in files["model.py"]
    validate_bundle_contract(files)


def test_generate_code_bundle_builds_manifest() -> None:
    spec = extract_build_spec("report", runner=_spec_ok)
    files, manifest = generate_code_bundle(spec, runner=_code_ok)
    assert manifest["spec_hash"] == build_spec_hash(spec)
    assert bundle_hash(manifest).startswith("sha256:")
    assert set(files) == {"model.py", "train.py", "infer.py"}


def test_generate_code_bundle_retries_on_contract_violation() -> None:
    calls: list[str] = []

    def broken_then_ok(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            # model.py misses build_model
            return _CODE_OUTPUT.replace(
                "def build_model(hyperparams: dict):",
                "def build_net(hyperparams: dict):",
            )
        return _CODE_OUTPUT

    spec = extract_build_spec("report", runner=_spec_ok)
    files, _ = generate_code_bundle(spec, runner=broken_then_ok)
    assert b"def build_model" in files["model.py"]
    assert len(calls) == 2


def test_generate_code_bundle_gives_up_after_retries() -> None:
    def always_broken(_prompt: str) -> str:
        return _CODE_OUTPUT.replace(
            "def train(data, spec: dict):", "def fit(data, spec: dict):"
        )

    spec = extract_build_spec("report", runner=_spec_ok)
    with pytest.raises(ValueError):
        generate_code_bundle(spec, runner=always_broken)
