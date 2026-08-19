"""Tests for factor build spec/bundle persistence and freeze discipline."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.factor_construction.artifacts import build_code_bundle, bundle_hash
from quant_platform.factor_construction.repository import (
    SqlAlchemyFactorConstructionRepository,
)
from quant_platform.factor_construction.schemas import FactorBuildSpecState
from quant_platform.factor_construction.spec import FactorBuildSpec
from quant_platform.research.models import Base


def make_repository() -> SqlAlchemyFactorConstructionRepository:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return SqlAlchemyFactorConstructionRepository(engine)


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
        },
        "architecture": "MLP",
        "style_neutralize": ["size", "volatility", "reversal", "liquidity"],
        "sample_weighting": "INVERSE_SIZE",
        "expected_direction": "POSITIVE",
    }
    values.update(overrides)
    return FactorBuildSpec.model_validate(values)


def _files() -> dict[str, bytes]:
    return {
        "model.py": b"def build_model(hyperparams: dict):\n    return None\n",
        "train.py": b"def train(data, spec: dict):\n    return None\n",
        "infer.py": b"def infer(data, weights):\n    return None\n",
    }


def test_create_spec_is_draft_and_content_addressed() -> None:
    repo = make_repository()
    record = repo.create_spec(actor_id="researcher-1", spec=make_spec())
    assert record.state is FactorBuildSpecState.DRAFT
    assert record.spec_hash.startswith("sha256:")
    assert record.spec.label.horizon == 21


def test_duplicate_spec_rejected() -> None:
    repo = make_repository()
    repo.create_spec(actor_id="researcher-1", spec=make_spec())
    with pytest.raises(ValueError):
        repo.create_spec(actor_id="researcher-2", spec=make_spec())


def test_freeze_spec_transitions_to_frozen() -> None:
    repo = make_repository()
    record = repo.create_spec(actor_id="researcher-1", spec=make_spec())
    frozen = repo.freeze_spec(
        spec_id=record.id,
        actor_id="researcher-1",
        expected_resource_version=1,
    )
    assert frozen.state is FactorBuildSpecState.FROZEN
    assert frozen.frozen_by == "researcher-1"
    assert frozen.frozen_at is not None


def test_frozen_spec_cannot_be_refrozen() -> None:
    repo = make_repository()
    record = repo.create_spec(actor_id="researcher-1", spec=make_spec())
    frozen = repo.freeze_spec(
        spec_id=record.id, actor_id="researcher-1", expected_resource_version=1
    )
    with pytest.raises(ValueError):
        repo.freeze_spec(
            spec_id=frozen.id, actor_id="researcher-1", expected_resource_version=2
        )


def test_freeze_requires_current_version() -> None:
    repo = make_repository()
    record = repo.create_spec(actor_id="researcher-1", spec=make_spec())
    with pytest.raises(ValueError):
        repo.freeze_spec(
            spec_id=record.id, actor_id="researcher-1", expected_resource_version=99
        )


def test_bundle_requires_frozen_spec() -> None:
    repo = make_repository()
    record = repo.create_spec(actor_id="researcher-1", spec=make_spec())
    manifest = build_code_bundle(_files(), spec_hash=record.spec_hash)
    with pytest.raises(ValueError):
        repo.create_bundle(
            actor_id="researcher-1",
            spec_hash=record.spec_hash,
            bundle_hash=bundle_hash(manifest),
            manifest=manifest,
        )


def test_bundle_created_against_frozen_spec() -> None:
    repo = make_repository()
    record = repo.create_spec(actor_id="researcher-1", spec=make_spec())
    repo.freeze_spec(
        spec_id=record.id, actor_id="researcher-1", expected_resource_version=1
    )
    manifest = build_code_bundle(_files(), spec_hash=record.spec_hash)
    bundle = repo.create_bundle(
        actor_id="researcher-1",
        spec_hash=record.spec_hash,
        bundle_hash=bundle_hash(manifest),
        manifest=manifest,
    )
    assert bundle.bundle_hash.startswith("sha256:")
    assert repo.get_bundle(bundle.bundle_hash) is not None


def test_bundle_rejects_spec_mismatch() -> None:
    repo = make_repository()
    record = repo.create_spec(actor_id="researcher-1", spec=make_spec())
    repo.freeze_spec(
        spec_id=record.id, actor_id="researcher-1", expected_resource_version=1
    )
    manifest = build_code_bundle(_files(), spec_hash="sha256:" + "b" * 64)
    with pytest.raises(ValueError):
        repo.create_bundle(
            actor_id="researcher-1",
            spec_hash=record.spec_hash,
            bundle_hash=bundle_hash(manifest),
            manifest=manifest,
        )
