"""Tests for frozen strategy artifacts (content addressing + tamper detection)."""

from __future__ import annotations

import pytest

from quant_platform.artifacts.store import (
    ArtifactCorruptionError,
    InMemoryArtifactStore,
)
from quant_platform.paper.artifact import (
    ArtifactAddressError,
    FrozenStrategyArtifact,
    StrategyArtifactStore,
)


def _artifact(code: str = "class S(Strategy): ...") -> FrozenStrategyArtifact:
    return FrozenStrategyArtifact(
        draft_id="sd_1",
        market="CN_A",
        instrument_ids=("600000.SH",),
        frequency="1d",
        code=code,
    )


def test_freeze_load_round_trip() -> None:
    store = StrategyArtifactStore(InMemoryArtifactStore())
    address = store.freeze(_artifact())
    loaded = store.load(address)
    assert loaded == _artifact()


def test_same_content_same_address() -> None:
    store = StrategyArtifactStore(InMemoryArtifactStore())
    first = store.freeze(_artifact())
    second = store.freeze(_artifact())
    assert first == second


def test_different_content_different_address() -> None:
    store = StrategyArtifactStore(InMemoryArtifactStore())
    first = store.freeze(_artifact("class A..."))
    second = store.freeze(_artifact("class B..."))
    assert first != second


def test_unknown_address_rejected() -> None:
    store = StrategyArtifactStore(InMemoryArtifactStore())
    with pytest.raises(ArtifactAddressError):
        store.load("sha256:" + "0" * 64)


def test_corrupted_payload_detected() -> None:
    inner = InMemoryArtifactStore()
    store = StrategyArtifactStore(inner)
    address = store.freeze(_artifact())
    # Tamper with the stored bytes behind the store's back.
    inner._objects[address] = b"tampered"  # noqa: SLF001
    with pytest.raises((ArtifactAddressError, ArtifactCorruptionError)):
        store.load(address)
