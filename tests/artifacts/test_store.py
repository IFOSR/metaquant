from __future__ import annotations

import json

import pytest

from quant_platform.artifacts import (
    ArtifactCorruptionError,
    ArtifactManifest,
    ArtifactNotFoundError,
    InMemoryArtifactStore,
    canonical_bytes,
    content_hash,
)


def test_canonical_bytes_and_hash_are_order_independent() -> None:
    left = {"schema_version": "test/v1", "payload": {"b": 2, "a": 1}}
    right = {"payload": {"a": 1, "b": 2}, "schema_version": "test/v1"}

    assert canonical_bytes(left) == canonical_bytes(right)
    assert json.loads(canonical_bytes(left)) == left
    assert content_hash(canonical_bytes(left)).startswith("sha256:")


def test_in_memory_store_is_immutable_idempotent_and_verifiable() -> None:
    store = InMemoryArtifactStore()
    payload = canonical_bytes({"schema_version": "factor/v1", "values": [1, 2]})

    first = store.put(payload, media_type="application/json")
    replay = store.put(payload, media_type="application/json")

    assert replay == first
    assert store.exists(first.content_hash)
    assert store.get(first.content_hash) == payload
    assert store.verify(first)


def test_store_fails_closed_for_missing_corrupt_or_conflicting_content() -> None:
    store = InMemoryArtifactStore()
    manifest = store.put(b"original", media_type="application/octet-stream")

    with pytest.raises(ArtifactNotFoundError):
        store.get("sha256:" + "0" * 64)

    store._objects[manifest.content_hash] = b"tampered"
    with pytest.raises(ArtifactCorruptionError):
        store.get(manifest.content_hash)
    assert not store.verify(manifest)


def test_manifest_rejects_latest_and_invalid_hashes() -> None:
    with pytest.raises(ValueError, match="latest"):
        ArtifactManifest(
            content_hash="latest",
            size_bytes=1,
            media_type="application/json",
        )
    with pytest.raises(ValueError, match="sha256"):
        ArtifactManifest(
            content_hash="not-a-hash",
            size_bytes=1,
            media_type="application/json",
        )
