from __future__ import annotations

from typing import Protocol

from quant_platform.data_gateway.models import (
    ArtifactClass,
    FrozenSnapshot,
    PITRow,
    SnapshotQuery,
    SnapshotSlice,
)


class SnapshotStore(Protocol):
    def _frozen_snapshot(self, snapshot_id: str) -> FrozenSnapshot:
        """Resolve a sealed snapshot for the domain gateway only."""


class InMemorySnapshotStore:
    """Representative immutable snapshot catalog, not a raw-table adapter."""

    def __init__(self, snapshots: tuple[FrozenSnapshot, ...]) -> None:
        self.__snapshots = {item.snapshot_id: item for item in snapshots}
        if len(self.__snapshots) != len(snapshots):
            raise ValueError("snapshot_id values must be unique")

    def _frozen_snapshot(self, snapshot_id: str) -> FrozenSnapshot:
        try:
            return self.__snapshots[snapshot_id]
        except KeyError as exc:
            raise KeyError(f"unknown frozen snapshot: {snapshot_id}") from exc


class PITDataGateway:
    def __init__(self, snapshots: SnapshotStore) -> None:
        self._snapshots = snapshots

    def query(self, request: SnapshotQuery) -> SnapshotSlice:
        snapshot = self._snapshots._frozen_snapshot(request.snapshot_id)
        if snapshot.artifact_class is ArtifactClass.EXPLORATORY:
            raise PermissionError("EXPLORATORY artifact cannot enter formal query")
        try:
            contract = snapshot.contracts[request.dataset_id]
        except KeyError as exc:
            raise KeyError(
                f"dataset {request.dataset_id} is not in snapshot {request.snapshot_id}"
            ) from exc

        contract.assert_formal()
        for field_name in request.fields:
            contract.field(field_name).assert_access(
                request.purpose,
                request.allowed_license_tags,
            )

        visible = (
            item
            for item in snapshot.rows
            if item.dataset_id == request.dataset_id
            and item.field in request.fields
            and item.available_time <= request.decision_time
            and item.license_tag in request.allowed_license_tags
        )
        revisions: dict[tuple[str, str, str, object], PITRow] = {}
        for item in visible:
            previous = revisions.get(item.revision_key)
            if previous is None or self._revision_order(item) > self._revision_order(
                previous
            ):
                revisions[item.revision_key] = item

        rows = tuple(
            sorted(
                revisions.values(),
                key=lambda item: (
                    item.event_time,
                    item.instrument_id,
                    item.field,
                    item.available_time,
                    item.revision_id,
                ),
            )
        )
        return SnapshotSlice(
            snapshot_id=snapshot.snapshot_id,
            dataset_id=request.dataset_id,
            decision_time=request.decision_time,
            purpose=request.purpose,
            rows=rows,
        )

    @staticmethod
    def _revision_order(item: PITRow) -> tuple[object, ...]:
        return (item.available_time, item.ingested_at, item.revision_id)
