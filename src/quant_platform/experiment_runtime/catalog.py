from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from quant_platform.experiments import canonical_hash


class FormalSnapshotCatalog(Protocol):
    def resolve(self, snapshot_id: str, manifest_hash: str) -> dict[str, Any]: ...
    def list(self) -> list[dict[str, Any]]: ...
    def register(self, payload: dict[str, Any]) -> None: ...


class InMemoryFormalSnapshotCatalog:
    def __init__(self, snapshots: tuple[dict[str, Any], ...]) -> None:
        self._snapshots = {str(item["snapshot_id"]): dict(item) for item in snapshots}
        if len(self._snapshots) != len(snapshots):
            raise ValueError("formal snapshot ids must be unique")
        for payload in self._snapshots.values():
            if (
                payload.get("sealed") is not True
                or payload.get("artifact_class") != "FORMAL"
            ):
                raise ValueError("catalog accepts only sealed FORMAL snapshots")

    def resolve(self, snapshot_id: str, manifest_hash: str) -> dict[str, Any]:
        try:
            payload = self._snapshots[snapshot_id]
        except KeyError as exc:
            raise ValueError("FORMAL_SNAPSHOT_NOT_REGISTERED") from exc
        if canonical_hash(payload) != manifest_hash:
            raise ValueError("SNAPSHOT_MANIFEST_HASH_MISMATCH")
        return dict(payload)

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "snapshot_id": snapshot_id,
                "manifest_hash": canonical_hash(payload),
                "market": payload.get("market"),
                "universe_ref": payload.get("universe_ref"),
                "frequency": payload.get("frequency"),
                "decision_clock": payload.get("decision_clock"),
                "trade_clock": payload.get("trade_clock"),
                "frozen_at": payload.get("frozen_at"),
                "instruments": sorted(
                    {str(row["instrument_id"]) for row in payload.get("rows", [])}
                ),
            }
            for snapshot_id, payload in sorted(self._snapshots.items())
        ]

    def register(self, payload: dict[str, Any]) -> None:
        """运行时注册一个密封快照（按需数据供给用）。"""
        if (
            payload.get("sealed") is not True
            or payload.get("artifact_class") != "FORMAL"
        ):
            raise ValueError("catalog accepts only sealed FORMAL snapshots")
        self._snapshots[str(payload["snapshot_id"])] = dict(payload)


class JsonFormalSnapshotCatalog(InMemoryFormalSnapshotCatalog):
    @classmethod
    def from_path(cls, path: Path) -> JsonFormalSnapshotCatalog:
        document = json.loads(path.read_text())
        if not isinstance(document, list):
            raise ValueError("formal snapshot catalog must be a JSON array")
        return cls(tuple(cast(list[dict[str, Any]], document)))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _execution_code_sha() -> str:
    """Derive the execution code SHA from the executor and IR source files."""
    pkg_root = Path(__file__).resolve().parent.parent
    digest = hashlib.sha256()
    for subpackage in ("factor_ir", "factor_executor", "experiment_runtime"):
        for path in sorted((pkg_root / subpackage).glob("*.py")):
            digest.update(path.read_bytes())
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    code_sha: str
    image_digest: str
    dependency_lock_hash: str
    executor_version: str
    config_hash: str

    @classmethod
    def resolved(
        cls,
        *,
        code_sha: str,
        image_digest: str,
        dependency_lock_hash: str,
        executor_version: str,
        config_hash: str,
        dependency_lock_path: Path = Path("uv.lock"),
        config_path: Path = Path("config/formal-snapshots.json"),
    ) -> ExecutionIdentity:
        """Fill placeholder content hashes with values derived from files.

        ``code_sha``, ``dependency_lock_hash``, and ``config_hash`` are content
        hashes: when a caller leaves the zero placeholder, they are derived
        from the actual source, lock, and snapshot-catalog files so the run
        fingerprint genuinely pins the executing code. ``image_digest`` and
        ``executor_version`` are identifiers supplied by the deployment and are
        passed through unchanged.
        """
        return cls(
            code_sha=code_sha
            if code_sha != "0" * len(code_sha)
            else _execution_code_sha(),
            image_digest=image_digest,
            dependency_lock_hash=(
                dependency_lock_hash
                if dependency_lock_hash != "0" * len(dependency_lock_hash)
                else _file_sha256(dependency_lock_path)
            ),
            executor_version=executor_version,
            config_hash=(
                config_hash
                if config_hash != "0" * len(config_hash)
                else _file_sha256(config_path)
            ),
        )
