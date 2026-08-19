"""End-to-end tests for the train/infer/validate service."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.artifacts.store import InMemoryArtifactStore
from quant_platform.factor_construction.artifacts import build_code_bundle, bundle_hash
from quant_platform.factor_construction.executor import FactorBuildExecutionError
from quant_platform.factor_construction.repository import (
    SqlAlchemyFactorConstructionRepository,
)
from quant_platform.factor_construction.service import FactorBuildService
from quant_platform.factor_construction.spec import FactorBuildSpec
from quant_platform.research.models import Base
from quant_platform.validation.model_factor import validate_model_factor

_MODEL = b"""def build_model(hyperparams: dict):
    return None
"""

_TRAIN = b"""import numpy as np

def train(data, labels, spec):
    return {"coef": [1.0] * data.data.shape[1]}
"""

_INFER = b"""import numpy as np

def infer(data, weights):
    return (data.data.values @ np.array(weights["coef"])).tolist()
"""

_FILES = {"model.py": _MODEL, "train.py": _TRAIN, "infer.py": _INFER}

_FEATURES = [
    {"instrument_id": "A", "event_time": "2026-08-01T07:00:00Z", "a": 1.0, "b": 2.0},
    {"instrument_id": "B", "event_time": "2026-08-01T07:00:00Z", "a": 3.0, "b": 4.0},
]

_LABELS = [
    {"instrument_id": "A", "event_time": "2026-08-01T07:00:00Z", "label": 0.05},
    {"instrument_id": "B", "event_time": "2026-08-01T07:00:00Z", "label": -0.03},
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


class _FakeData:
    def pit_frame(
        self, *, instrument_ids, fields, decision_time, field_prefix="market.eod."
    ):
        return {"rows": _FEATURES}

    def label_frame(
        self,
        *,
        instrument_ids,
        price_field,
        horizon,
        decision_time,
        field_prefix="market.eod.",
        return_type="simple",
    ):
        return {"rows": _LABELS}


class _FailingData:
    def pit_frame(self, **kwargs):
        raise ValueError("data unavailable")

    def label_frame(self, **kwargs):
        return {"rows": []}


def _repository() -> SqlAlchemyFactorConstructionRepository:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return SqlAlchemyFactorConstructionRepository(engine)


def _register_bundle(
    repository: SqlAlchemyFactorConstructionRepository,
    artifacts: InMemoryArtifactStore,
    spec: FactorBuildSpec,
) -> tuple[str, str]:
    record = repository.create_spec(actor_id="researcher-1", spec=spec)
    repository.freeze_spec(
        spec_id=record.id, actor_id="researcher-1", expected_resource_version=1
    )
    manifest = build_code_bundle(_FILES, spec_hash=record.spec_hash)
    repository.create_bundle(
        actor_id="researcher-1",
        spec_hash=record.spec_hash,
        bundle_hash=bundle_hash(manifest),
        manifest=manifest,
        files=_FILES,
        artifact_store=artifacts,
    )
    return record.spec_hash, bundle_hash(manifest)


def test_train_infer_validate_roundtrip() -> None:
    repository = _repository()
    artifacts = InMemoryArtifactStore()
    service = FactorBuildService(repository, artifacts, _FakeData())  # type: ignore[arg-type]
    spec_hash, bundle = _register_bundle(repository, artifacts, _spec())

    train = service.train(
        spec_hash=spec_hash,
        bundle_hash=bundle,
        instrument_ids=["A", "B"],
        decision_time="2026-08-02T07:00:00Z",
    )
    assert train.weights_hash.startswith("sha256:")
    assert train.run.state.value == "SUCCEEDED"

    infer = service.infer(
        spec_hash=spec_hash,
        bundle_hash=bundle,
        weights_hash=train.weights_hash,
        instrument_ids=["A", "B"],
        decision_time="2026-08-02T07:00:00Z",
    )
    assert infer.run.state.value == "SUCCEEDED"
    assert infer.run.factor_values_hash is not None

    factor_rows = [
        {
            "instrument_id": obs.instrument_id,
            "event_time": obs.timestamp.isoformat(),
            "value": obs.value,
        }
        for obs in infer.observations
    ]
    label_rows = [
        {"instrument_id": "A", "event_time": "2026-08-01T07:00:00Z", "value": 0.05},
        {"instrument_id": "B", "event_time": "2026-08-01T07:00:00Z", "value": -0.03},
    ]
    report = validate_model_factor(factor_rows, label_rows)
    assert report.observation_count == 2
    assert report.pearson_ic is not None
    assert len(report.output_hash) == 64


def test_train_failure_marks_run_failed() -> None:
    repository = _repository()
    artifacts = InMemoryArtifactStore()
    service = FactorBuildService(repository, artifacts, _FakeData())  # type: ignore[arg-type]
    spec_hash, bundle = _register_bundle(repository, artifacts, _spec())
    service._data = _FailingData()  # type: ignore[assignment]

    with pytest.raises(FactorBuildExecutionError):
        service.train(
            spec_hash=spec_hash,
            bundle_hash=bundle,
            instrument_ids=["A", "B"],
            decision_time="2026-08-02T07:00:00Z",
        )
    runs = [
        repository.get_run(run_id)
        for run_id in _all_run_ids(repository)
        if repository.get_run(run_id) is not None
    ]
    assert any(run.state.value == "FAILED" for run in runs)


def _all_run_ids(repository: SqlAlchemyFactorConstructionRepository) -> list[str]:
    # The repository has no list-runs; query the model directly for the test.
    from sqlalchemy import select

    from quant_platform.research.models import FactorBuildRunModel

    with repository._sessions() as session:  # type: ignore[attr-defined]
        return list(session.scalars(select(FactorBuildRunModel.id)).all())
