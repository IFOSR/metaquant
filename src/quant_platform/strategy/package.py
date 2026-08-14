"""StrategyPackage contracts (G10-002).

An immutable, signed, content-addressed strategy package. The package payload
binds a ``StrategySpec`` to its data manifest and the formal backtest result it
consumed. Approval, rejection, expiry, and revocation are NOT part of the
package; they are expressed by separate attestations bound to the package
content hash. Signatures use HMAC-SHA256 over the content hash so the signature
never changes the content hash.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from quant_platform.experiments import canonical_hash
from quant_platform.strategy.spec import StrategySpec

_HEX_DIGITS = frozenset("0123456789abcdef")


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(ch not in _HEX_DIGITS for ch in value):
        raise ValueError(f"{name} must be a 64-character hex digest")


@dataclass(frozen=True, slots=True)
class DataManifest:
    snapshot_id: str
    snapshot_manifest_hash: str
    rule_version: str
    code_version: str
    dependency_lock_hash: str

    def __post_init__(self) -> None:
        _require_identifier(self.snapshot_id, "snapshot_id")
        _require_sha256(self.snapshot_manifest_hash, "snapshot_manifest_hash")
        _require_identifier(self.rule_version, "rule_version")
        _require_identifier(self.code_version, "code_version")
        _require_sha256(self.dependency_lock_hash, "dependency_lock_hash")

    def payload(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_manifest_hash": self.snapshot_manifest_hash,
            "rule_version": self.rule_version,
            "code_version": self.code_version,
            "dependency_lock_hash": self.dependency_lock_hash,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


@dataclass(frozen=True, slots=True)
class StrategyPackage:
    package_id: str
    spec: StrategySpec
    data_manifest: DataManifest
    backtest_result_hash: str
    signature: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.package_id, "package_id")
        _require_sha256(self.backtest_result_hash, "backtest_result_hash")
        if self.signature is not None and not _HEX_DIGITS.issuperset(self.signature):
            raise ValueError("signature must be a lowercase hex digest")

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "schema_version": "strategy-package/v1",
            "package_id": self.package_id,
            "spec": self.spec.payload(),
            "data_manifest": self.data_manifest.payload(),
            "backtest_result_hash": self.backtest_result_hash,
        }

    def content_hash(self) -> str:
        """Content hash over the unsigned payload (signature excluded)."""
        return canonical_hash(self.unsigned_payload())

    def sign(self, key: bytes) -> StrategyPackage:
        """Return a copy carrying an HMAC-SHA256 signature over the content hash."""
        if not key:
            raise ValueError("signing key must not be empty")
        digest = hmac.new(key, self.content_hash().encode(), hashlib.sha256).hexdigest()
        return StrategyPackage(
            package_id=self.package_id,
            spec=self.spec,
            data_manifest=self.data_manifest,
            backtest_result_hash=self.backtest_result_hash,
            signature=digest,
        )

    def verify(self, key: bytes) -> bool:
        """Verify the package signature against the content hash."""
        if self.signature is None or not key:
            return False
        expected = hmac.new(
            key, self.content_hash().encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)


def build_package(
    *,
    package_id: str,
    spec: StrategySpec,
    data_manifest: DataManifest,
    backtest_result_hash: str,
) -> StrategyPackage:
    """Assemble an unsigned, content-addressed strategy package."""
    return StrategyPackage(
        package_id=package_id,
        spec=spec,
        data_manifest=data_manifest,
        backtest_result_hash=backtest_result_hash,
    )


def verify_package(package: StrategyPackage, key: bytes) -> bool:
    """Return True only when the package signature matches its content hash."""
    return package.verify(key)
