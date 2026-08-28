"""Frozen strategy artifacts for paper accounts (content-addressed).

The draft table row is mutable history; a paper account must run against an
immutable snapshot. Freezing serializes the strategy payload into canonical
bytes, stores them in the content-addressed :class:`ArtifactStore` (MinIO in
production), and returns the address. Loading re-verifies the hash so any
tampering is detected before a strategy is allowed to trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quant_platform.artifacts.store import (
    ArtifactCorruptionError,
    ArtifactNotFoundError,
    ArtifactStore,
    canonical_bytes,
)


class ArtifactAddressError(ValueError):
    """Raised when a stored artifact does not match its address."""


@dataclass(frozen=True, slots=True)
class FrozenStrategyArtifact:
    """Immutable snapshot of a frozen strategy draft."""

    draft_id: str
    market: str
    instrument_ids: tuple[str, ...]
    frequency: str
    code: str

    def to_bytes(self) -> bytes:
        payload: dict[str, Any] = {
            "schema_version": "paper-strategy-artifact/v1",
            "draft_id": self.draft_id,
            "market": self.market,
            "instrument_ids": list(self.instrument_ids),
            "frequency": self.frequency,
            "code": self.code,
        }
        return canonical_bytes(payload)

    @classmethod
    def from_bytes(cls, payload: bytes) -> FrozenStrategyArtifact:
        import json

        data = json.loads(payload)
        if data.get("schema_version") != "paper-strategy-artifact/v1":
            raise ArtifactAddressError(
                f"unsupported artifact schema: {data.get('schema_version')}"
            )
        return cls(
            draft_id=str(data["draft_id"]),
            market=str(data["market"]),
            instrument_ids=tuple(str(item) for item in data["instrument_ids"]),
            frequency=str(data["frequency"]),
            code=str(data["code"]),
        )


class StrategyArtifactStore:
    """Freeze/load strategy payloads against a content-addressed store."""

    def __init__(self, store: ArtifactStore) -> None:
        self._store = store

    def freeze(self, artifact: FrozenStrategyArtifact) -> str:
        """Persist the artifact; returns its content address."""
        manifest = self._store.put(artifact.to_bytes(), media_type="application/json")
        return manifest.content_hash

    def load(self, address: str) -> FrozenStrategyArtifact:
        """Load an artifact by address; the store verifies the hash on read."""
        try:
            payload = self._store.get(address)
        except (ArtifactNotFoundError, ArtifactCorruptionError) as exc:
            raise ArtifactAddressError(
                f"artifact unavailable at {address}: {exc}"
            ) from exc
        return FrozenStrategyArtifact.from_bytes(payload)
