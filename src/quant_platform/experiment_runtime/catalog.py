from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from quant_platform.experiments import canonical_hash


class FormalSnapshotCatalog(Protocol):
    def resolve(self, snapshot_id: str, manifest_hash: str) -> dict[str, Any]: ...


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


class JsonFormalSnapshotCatalog(InMemoryFormalSnapshotCatalog):
    @classmethod
    def from_path(cls, path: Path) -> JsonFormalSnapshotCatalog:
        document = json.loads(path.read_text())
        if not isinstance(document, list):
            raise ValueError("formal snapshot catalog must be a JSON array")
        return cls(tuple(cast(list[dict[str, Any]], document)))


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    code_sha: str
    image_digest: str
    dependency_lock_hash: str
    executor_version: str
    config_hash: str
