"""Tests for sandbox train/infer execution (numpy bundle, no torch needed)."""

from __future__ import annotations

from quant_platform.factor_construction.executor import run_infer, run_train
from quant_platform.factor_construction.spec import FactorBuildSpec

_MODEL = b"""def build_model(hyperparams: dict):
    return None
"""

_TRAIN = b"""import numpy as np

def train(data, labels, spec):
    n = data.data.shape[1]
    return {"coef": [1.0] * n}
"""

_INFER = b"""import numpy as np

def infer(data, weights):
    X = data.data.values
    coef = np.array(weights["coef"])
    return (X @ coef).tolist()
"""

_BUNDLE = {"model.py": _MODEL, "train.py": _TRAIN, "infer.py": _INFER}

_DATA_ROWS = [
    {"instrument_id": "A", "event_time": "2026-08-01T07:00:00Z", "a": 1.0, "b": 2.0},
    {"instrument_id": "B", "event_time": "2026-08-01T07:00:00Z", "a": 3.0, "b": 4.0},
]


def _spec() -> FactorBuildSpec:
    return FactorBuildSpec.model_validate(
        {
            "factor_id": "cn_a.demo_linear",
            "factor_name": "DemoLinear",
            "market": "CN_A",
            "universe_ref": "u",
            "inputs": ["a", "b"],
            "label": {"name": "future_return", "price_field": "a", "horizon": 1},
            "architecture": "LINEAR",
        }
    )


def test_run_train_produces_content_addressed_weights() -> None:
    outcome = run_train(
        bundle_files=_BUNDLE,
        spec=_spec(),
        data_rows=_DATA_ROWS,
        fields=["a", "b"],
        label_rows=[],
        decision_time="2026-08-02T07:00:00Z",
    )
    assert outcome.weights_hash.startswith("sha256:")
    assert outcome.weights


def test_run_infer_returns_factor_observations() -> None:
    trained = run_train(
        bundle_files=_BUNDLE,
        spec=_spec(),
        data_rows=_DATA_ROWS,
        fields=["a", "b"],
        label_rows=[],
        decision_time="2026-08-02T07:00:00Z",
    )
    outcome = run_infer(
        bundle_files=_BUNDLE,
        spec=_spec(),
        weights=trained.weights,
        data_rows=_DATA_ROWS,
        fields=["a", "b"],
        decision_time="2026-08-02T07:00:00Z",
    )
    by_instrument = {obs.instrument_id: obs.value for obs in outcome.observations}
    assert by_instrument["A"] == 3.0  # 1 + 2
    assert by_instrument["B"] == 7.0  # 3 + 4
    assert len(outcome.output_hash) == 64
