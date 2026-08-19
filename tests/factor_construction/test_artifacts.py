"""Tests for the three-file code bundle (code-bundle/v1)."""

from __future__ import annotations

import pytest

from quant_platform.factor_construction.artifacts import (
    CodeBundleError,
    build_code_bundle,
    validate_bundle_contract,
)

MODEL_PY = b"""def build_model(hyperparams: dict):
    import torch
    return torch.nn.Sequential(
        torch.nn.Linear(
            hyperparams.get("input_dim", 7), hyperparams.get("hidden_dim", 64)
        ),
        torch.nn.ReLU(),
        torch.nn.Linear(hyperparams.get("hidden_dim", 64), 1),
    )
"""

TRAIN_PY = b"""def train(data, spec: dict):
    import torch
    features = data.data.values
    model = build_model(spec["hyperparameters"])
    return model
"""

INFER_PY = b"""def infer(data, weights):
    model = build_model({})
    model.load_state_dict(weights)
    return model(data.data.values)
"""


def _files(**overrides: bytes) -> dict[str, bytes]:
    files = {"model.py": MODEL_PY, "train.py": TRAIN_PY, "infer.py": INFER_PY}
    files.update(overrides)
    return files


def test_bundle_hash_is_stable() -> None:
    first = build_code_bundle(_files(), spec_hash="sha256:" + "a" * 64)
    second = build_code_bundle(_files(), spec_hash="sha256:" + "a" * 64)
    assert first == second
    assert first["schema_version"] == "code-bundle/v1"
    assert set(first["files"]) == {"model.py", "train.py", "infer.py"}


def test_bundle_hash_changes_when_file_changes() -> None:
    first = build_code_bundle(_files(), spec_hash="sha256:" + "a" * 64)
    second = build_code_bundle(
        _files(**{"train.py": TRAIN_PY + b"\n# tweaked\n"}),
        spec_hash="sha256:" + "a" * 64,
    )
    assert first != second


def test_bundle_requires_exactly_three_files() -> None:
    with pytest.raises(CodeBundleError):
        build_code_bundle(
            {"model.py": MODEL_PY, "train.py": TRAIN_PY},
            spec_hash="sha256:" + "a" * 64,
        )


def test_bundle_rejects_missing_contract_symbol() -> None:
    with pytest.raises(CodeBundleError):
        validate_bundle_contract(
            _files(**{"infer.py": b"def predict(data, weights):\n    return None\n"})
        )


def test_bundle_rejects_syntax_error() -> None:
    with pytest.raises(CodeBundleError):
        validate_bundle_contract(
            _files(**{"model.py": b"def build_model(:\n    pass\n"})
        )


def test_contract_accepts_valid_bundle() -> None:
    validate_bundle_contract(_files())
