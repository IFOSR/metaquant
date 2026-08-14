"""Two-person lockbox contracts (G11-002).

A lockbox protects a sealed value behind two independent keys. Unlocking
requires both distinct keys to match their guards, enforcing separation of
duties. The lockbox stores only hashes, never the keys or the plaintext.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from quant_platform.experiments import canonical_hash

_HEX_DIGITS = frozenset("0123456789abcdef")


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(ch not in _HEX_DIGITS for ch in value):
        raise ValueError(f"{name} must be a 64-character hex digest")


def key_hash(key: str) -> str:
    if not key:
        raise ValueError("key must not be empty")
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Lockbox:
    box_id: str
    sealed_hash: str
    guard1_hash: str
    guard2_hash: str

    def __post_init__(self) -> None:
        _require_identifier(self.box_id, "box_id")
        _require_sha256(self.sealed_hash, "sealed_hash")
        _require_sha256(self.guard1_hash, "guard1_hash")
        _require_sha256(self.guard2_hash, "guard2_hash")
        if self.guard1_hash == self.guard2_hash:
            raise ValueError("lockbox guards must be distinct")

    def unlock(self, key1: str, key2: str) -> bool:
        """Return True only when both distinct keys match their guards."""
        if not key1 or not key2 or key1 == key2:
            return False
        h1, h2 = key_hash(key1), key_hash(key2)
        return (h1 == self.guard1_hash and h2 == self.guard2_hash) or (
            h1 == self.guard2_hash and h2 == self.guard1_hash
        )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "lockbox/v1",
            "box_id": self.box_id,
            "sealed_hash": self.sealed_hash,
            "guard1_hash": self.guard1_hash,
            "guard2_hash": self.guard2_hash,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def build_lockbox(
    *, box_id: str, sealed_hash: str, guard1_key: str, guard2_key: str
) -> Lockbox:
    """Create a lockbox from two distinct guard keys."""
    if guard1_key == guard2_key:
        raise ValueError("guard keys must be distinct")
    return Lockbox(
        box_id=box_id,
        sealed_hash=sealed_hash,
        guard1_hash=key_hash(guard1_key),
        guard2_hash=key_hash(guard2_key),
    )
