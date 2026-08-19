"""Orchestration service: train/infer a code bundle and record the lineage.

Wires the repository (spec/bundle/run state) with the artifact store (bundle
files, weights, factor values), the PIT data service, and the sandbox executor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from quant_platform.artifacts.store import ArtifactStore, content_hash
from quant_platform.factor_construction.artifacts import (
    build_code_bundle,
)
from quant_platform.factor_construction.artifacts import (
    bundle_hash as compute_bundle_hash,
)
from quant_platform.factor_construction.executor import (
    FactorBuildExecutionError,
    InferOutcome,
    TrainOutcome,
    run_infer,
    run_train,
)
from quant_platform.factor_construction.repository import (
    SqlAlchemyFactorConstructionRepository,
)
from quant_platform.factor_construction.schemas import (
    FactorBuildRunKind,
    FactorBuildRunRecord,
    FactorCodeBundleRecord,
)
from quant_platform.factor_construction.spec import FactorBuildSpec
from quant_platform.validation.model_factor import (
    ModelFactorValidationReport,
    validate_model_factor,
)


class DataService(Protocol):
    def pit_frame(
        self,
        *,
        instrument_ids: tuple[str, ...],
        fields: tuple[str, ...],
        decision_time: Any,
        field_prefix: str = "market.eod.",
    ) -> dict[str, Any]: ...

    def label_frame(
        self,
        *,
        instrument_ids: tuple[str, ...],
        price_field: str,
        horizon: int,
        decision_time: Any,
        field_prefix: str = "market.eod.",
        return_type: str = "simple",
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class TrainResult:
    run: FactorBuildRunRecord
    weights_hash: str


@dataclass(frozen=True, slots=True)
class InferResult:
    run: FactorBuildRunRecord
    factor_values_hash: str
    output_hash: str
    observations: tuple[Any, ...]


class FactorBuildService:
    def __init__(
        self,
        repository: SqlAlchemyFactorConstructionRepository,
        artifact_store: ArtifactStore,
        data_service: DataService,
    ) -> None:
        self._repository = repository
        self._artifacts = artifact_store
        self._data = data_service

    def _spec(self, spec_hash: str) -> FactorBuildSpec:
        record = self._repository.get_spec_by_hash(spec_hash)
        if record is None:
            raise FactorBuildExecutionError("RESOURCE_NOT_FOUND")
        return record.spec

    def _bundle_files(self, bundle_hash: str) -> dict[str, bytes]:
        return self._repository.get_bundle_files(bundle_hash, self._artifacts)

    def register_bundle(
        self,
        *,
        actor_id: str,
        spec_hash: str,
        bundle_hash: str,
        manifest: dict[str, Any],
        files_text: dict[str, str],
    ) -> FactorCodeBundleRecord:
        """Verify files against the manifest, store them, and persist the bundle."""
        files = {name: text.encode() for name, text in files_text.items()}
        expected = build_code_bundle(files, spec_hash=spec_hash)
        if compute_bundle_hash(expected) != bundle_hash:
            raise FactorBuildExecutionError("BUNDLE_HASH_MISMATCH")
        return self._repository.create_bundle(
            actor_id=actor_id,
            spec_hash=spec_hash,
            bundle_hash=bundle_hash,
            manifest=manifest,
            files=files,
            artifact_store=self._artifacts,
        )

    def train(
        self,
        *,
        spec_hash: str,
        bundle_hash: str,
        instrument_ids: list[str],
        decision_time: str,
        field_prefix: str = "market.eod.",
    ) -> TrainResult:
        spec = self._spec(spec_hash)
        files = self._bundle_files(bundle_hash)
        run = self._repository.record_run(
            spec_hash=spec_hash, bundle_hash=bundle_hash, kind=FactorBuildRunKind.TRAIN
        )
        self._repository.mark_run_running(run.id)
        try:
            frame = self._data.pit_frame(
                instrument_ids=tuple(instrument_ids),
                fields=tuple(spec.inputs),
                decision_time=decision_time,
                field_prefix=field_prefix,
            )
            labels = self._data.label_frame(
                instrument_ids=tuple(instrument_ids),
                price_field=spec.label.price_field,
                horizon=spec.label.horizon,
                decision_time=decision_time,
                field_prefix=field_prefix,
            )
            outcome: TrainOutcome = run_train(
                bundle_files=files,
                spec=spec,
                data_rows=frame["rows"],
                fields=list(spec.inputs),
                label_rows=labels["rows"],
                decision_time=decision_time,
            )
        except (FactorBuildExecutionError, ValueError) as exc:
            self._repository.fail_run(run.id, str(exc))
            raise FactorBuildExecutionError(str(exc)) from exc
        self._artifacts.put(outcome.weights, media_type="application/octet-stream")
        completed = self._repository.complete_run(
            run.id, weights_hash=outcome.weights_hash
        )
        return TrainResult(run=completed, weights_hash=outcome.weights_hash)

    def infer(
        self,
        *,
        spec_hash: str,
        bundle_hash: str,
        weights_hash: str,
        instrument_ids: list[str],
        decision_time: str,
        field_prefix: str = "market.eod.",
    ) -> InferResult:
        spec = self._spec(spec_hash)
        files = self._bundle_files(bundle_hash)
        weights = self._artifacts.get(weights_hash)
        run = self._repository.record_run(
            spec_hash=spec_hash, bundle_hash=bundle_hash, kind=FactorBuildRunKind.INFER
        )
        self._repository.mark_run_running(run.id)
        try:
            frame = self._data.pit_frame(
                instrument_ids=tuple(instrument_ids),
                fields=tuple(spec.inputs),
                decision_time=decision_time,
                field_prefix=field_prefix,
            )
            outcome: InferOutcome = run_infer(
                bundle_files=files,
                spec=spec,
                weights=weights,
                data_rows=frame["rows"],
                fields=list(spec.inputs),
                decision_time=decision_time,
            )
        except (FactorBuildExecutionError, ValueError) as exc:
            self._repository.fail_run(run.id, str(exc))
            raise FactorBuildExecutionError(str(exc)) from exc
        self._artifacts.put(
            outcome.canonical_json.encode(),
            media_type="application/vnd.quant.factor-observations+json",
        )
        completed = self._repository.complete_run(
            run.id, factor_values_hash=content_hash(outcome.canonical_json.encode())
        )
        return InferResult(
            run=completed,
            factor_values_hash=content_hash(outcome.canonical_json.encode()),
            output_hash=outcome.output_hash,
            observations=outcome.observations,
        )

    def validate(
        self,
        *,
        factor_values_hash: str,
        instrument_ids: list[str],
        price_field: str,
        horizon: int,
        decision_time: str,
        field_prefix: str = "market.eod.",
        return_type: str = "simple",
    ) -> ModelFactorValidationReport:
        canonical_json = self._artifacts.get(factor_values_hash).decode()
        payload = json.loads(canonical_json)
        factor_rows = [
            {
                "instrument_id": item["instrument_id"],
                "event_time": item["timestamp"],
                "value": item["value"],
            }
            for item in payload["observations"]
        ]
        labels = self._data.label_frame(
            instrument_ids=tuple(instrument_ids),
            price_field=price_field,
            horizon=horizon,
            decision_time=decision_time,
            field_prefix=field_prefix,
            return_type=return_type,
        )
        label_rows = [
            {
                "instrument_id": row["instrument_id"],
                "event_time": row["event_time"],
                "value": row["label"],
            }
            for row in labels["rows"]
        ]
        return validate_model_factor(factor_rows, label_rows)
