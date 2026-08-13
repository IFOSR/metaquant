from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from quant_platform.experiments import (
    ArtifactManifest,
    Attempt,
    AttemptState,
    ExperimentRun,
    ExperimentRunState,
    ExperimentSpec,
    ExperimentSpecState,
    FactorComputationArtifact,
    FactorObservation,
    InvarianceEvidence,
    LineageEdge,
    LineageRelation,
    ResourceBudget,
    ValidationArtifact,
    ValidationSummary,
    canonical_hash,
    canonical_json,
    compute_run_fingerprint,
)


def at(hour: int = 0) -> datetime:
    return datetime(2026, 8, 12, hour, tzinfo=UTC)


def draft_spec() -> ExperimentSpec:
    return ExperimentSpec.draft(
        experiment_id="experiment-001",
        project_id="local",
        research_job_id="job-001",
        brief_version_id="brief-001",
        brief_content_hash="1" * 64,
        factor_ir_hash="2" * 64,
        snapshot_id="snapshot-001",
        snapshot_manifest_hash="3" * 64,
        market="CN_A",
        universe_ref="universe://csi300-pit/v1",
        frequency="1d",
        decision_time=at(),
        decision_clock="T_CLOSE+30m",
        trade_clock="T+1_OPEN",
        settlement_clock=None,
        exchange_scope=(),
        contract_chain_ref=None,
        roll_policy_ref=None,
        validation_policy_ref="policy://cn-a-daily-factor/v1",
        license_purpose="RESEARCH",
        allowed_license_tags=frozenset({"licensed-research"}),
        random_seed=41,
        resource_budget=ResourceBudget(
            cpu_seconds=300,
            wall_clock_seconds=600,
            memory_mb=2048,
            max_observations=1_000_000,
        ),
    )


def test_canonical_json_and_hash_ignore_mapping_and_set_order() -> None:
    left = {
        "market": "CN_A",
        "tags": frozenset({"beta", "alpha"}),
        "nested": {"b": 2, "a": 1},
        "when": at(),
    }
    right = {
        "when": at(),
        "nested": {"a": 1, "b": 2},
        "tags": frozenset({"alpha", "beta"}),
        "market": "CN_A",
    }

    assert canonical_json(left) == canonical_json(right)
    assert canonical_hash(left) == canonical_hash(right)
    assert canonical_json(left) == (
        '{"market":"CN_A","nested":{"a":1,"b":2},'
        '"tags":["alpha","beta"],"when":"2026-08-12T00:00:00Z"}'
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        canonical_json({"value": value})


def test_spec_preregistration_preserves_content_hash_and_freezes_revision() -> None:
    draft = draft_spec()
    revised = draft.revise(random_seed=42)
    preregistered = revised.preregister(actor_id="research-lead-1", at=at(1))

    assert draft.state is ExperimentSpecState.DRAFT
    assert revised.spec_hash != draft.spec_hash
    assert preregistered.state is ExperimentSpecState.PREREGISTERED
    assert preregistered.spec_hash == revised.spec_hash
    assert preregistered.preregistered_by == "research-lead-1"
    assert preregistered.preregistered_at == at(1)
    with pytest.raises(ValueError, match="immutable"):
        preregistered.revise(random_seed=43)
    with pytest.raises(FrozenInstanceError):
        preregistered.market = "CN_COMMODITY_FUTURES"  # type: ignore[misc]


def test_spec_rejects_latest_and_non_daily_formal_bindings() -> None:
    with pytest.raises(ValueError, match="latest"):
        draft_spec().revise(snapshot_id="snapshot://latest")
    with pytest.raises(ValueError, match="1d"):
        draft_spec().revise(frequency="5m")


def test_experiment_run_and_attempt_have_independent_state_machines() -> None:
    spec = draft_spec().preregister(actor_id="lead", at=at(1))
    run = ExperimentRun.queued(
        run_id="run-001",
        experiment_id=spec.experiment_id,
        experiment_spec_hash=spec.spec_hash,
        run_fingerprint="4" * 64,
        queued_at=at(2),
    )
    attempt = Attempt.queued(
        attempt_id="attempt-001",
        run_id=run.run_id,
        ordinal=1,
        queued_at=at(2),
    )

    running_attempt = attempt.transition(AttemptState.RUNNING, at=at(3))
    running_run = run.add_attempt(running_attempt).transition(
        ExperimentRunState.RUNNING,
        at=at(3),
    )
    succeeded_attempt = running_attempt.transition(AttemptState.SUCCEEDED, at=at(4))
    succeeded_run = running_run.transition(ExperimentRunState.SUCCEEDED, at=at(4))

    assert running_run.state is ExperimentRunState.RUNNING
    assert running_run.attempt_ids == ("attempt-001",)
    assert succeeded_attempt.state is AttemptState.SUCCEEDED
    assert succeeded_run.state is ExperimentRunState.SUCCEEDED
    assert running_attempt.state is AttemptState.RUNNING
    with pytest.raises(ValueError, match="invalid run transition"):
        succeeded_run.transition(ExperimentRunState.RUNNING, at=at(5))
    with pytest.raises(ValueError, match="invalid attempt transition"):
        succeeded_attempt.transition(AttemptState.RUNNING, at=at(5))


def test_retry_adds_a_new_attempt_without_overwriting_history() -> None:
    spec = draft_spec().preregister(actor_id="lead", at=at(1))
    first = Attempt.queued(
        attempt_id="attempt-001",
        run_id="run-001",
        ordinal=1,
        queued_at=at(2),
    ).transition(AttemptState.RUNNING, at=at(3))
    first = first.transition(AttemptState.FAILED, at=at(4))
    run = ExperimentRun.queued(
        run_id="run-001",
        experiment_id=spec.experiment_id,
        experiment_spec_hash=spec.spec_hash,
        run_fingerprint="4" * 64,
        queued_at=at(2),
    ).add_attempt(first)
    run = run.transition(ExperimentRunState.RUNNING, at=at(3)).transition(
        ExperimentRunState.FAILED_RETRYABLE,
        at=at(4),
    )
    second = Attempt.queued(
        attempt_id="attempt-002",
        run_id=run.run_id,
        ordinal=2,
        queued_at=at(5),
    )

    retried = run.add_attempt(second).transition(ExperimentRunState.RUNNING, at=at(5))

    assert retried.attempt_ids == ("attempt-001", "attempt-002")
    assert first.state is AttemptState.FAILED


def test_computation_validation_and_lineage_contracts_are_immutable() -> None:
    computation = FactorComputationArtifact.create(
        artifact_id="artifact-computation-001",
        run_id="run-001",
        attempt_id="attempt-001",
        experiment_spec_hash="1" * 64,
        factor_ir_hash="2" * 64,
        snapshot_id="snapshot-001",
        snapshot_manifest_hash="3" * 64,
        input_hash="4" * 64,
        observations=(
            FactorObservation(
                instrument_id="600000.SSE",
                event_time=at(),
                value=0.25,
            ),
            FactorObservation(
                instrument_id="000001.SZSE",
                event_time=at(),
                value=None,
            ),
        ),
    )
    validation = ValidationArtifact.create(
        artifact_id="artifact-validation-001",
        run_id="run-001",
        attempt_id="attempt-001",
        experiment_spec_hash="1" * 64,
        computation_artifact_hash=computation.manifest.content_hash,
        summary=ValidationSummary(
            observation_count=2,
            finite_count=1,
            missing_count=1,
            coverage_ratio=0.5,
            minimum=0.25,
            maximum=0.25,
            mean=0.25,
        ),
        invariance=InvarianceEvidence(
            future_truncation_passed=True,
            sentinel_isolation_passed=True,
            baseline_output_hash=computation.output_hash,
            future_truncation_output_hash=computation.output_hash,
            sentinel_isolation_output_hash=computation.output_hash,
        ),
        input_hash=computation.manifest.content_hash,
        output_hash="5" * 64,
    )
    edge = LineageEdge(
        source_artifact_hash=computation.manifest.content_hash,
        target_artifact_hash=validation.manifest.content_hash,
        relation=LineageRelation.VALIDATED_BY,
    )

    assert isinstance(computation.manifest, ArtifactManifest)
    assert computation.manifest.content_hash == canonical_hash(computation.payload())
    assert computation.output_hash == canonical_hash(computation.observations)
    assert validation.manifest.content_hash == canonical_hash(validation.payload())
    assert len(edge.edge_hash) == 64
    with pytest.raises(FrozenInstanceError):
        computation.output_hash = "6" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        edge.relation = LineageRelation.DERIVED_FROM  # type: ignore[misc]


def test_artifact_manifests_reject_tampering_and_invalid_summaries() -> None:
    computation = FactorComputationArtifact.create(
        artifact_id="artifact-computation-001",
        run_id="run-001",
        attempt_id="attempt-001",
        experiment_spec_hash="1" * 64,
        factor_ir_hash="2" * 64,
        snapshot_id="snapshot-001",
        snapshot_manifest_hash="3" * 64,
        input_hash="4" * 64,
        observations=(),
    )

    with pytest.raises(ValueError, match="manifest"):
        replace(
            computation,
            manifest=replace(computation.manifest, content_hash="9" * 64),
        )
    with pytest.raises(ValueError, match="counts"):
        ValidationSummary(
            observation_count=2,
            finite_count=2,
            missing_count=1,
            coverage_ratio=1.0,
            minimum=0.0,
            maximum=1.0,
            mean=0.5,
        )


def test_artifact_content_hashes_do_not_depend_on_run_instance_ids() -> None:
    shared = {
        "experiment_spec_hash": "1" * 64,
        "factor_ir_hash": "2" * 64,
        "snapshot_id": "snapshot-001",
        "snapshot_manifest_hash": "3" * 64,
        "input_hash": "4" * 64,
        "observations": (
            FactorObservation(
                instrument_id="600000.SSE",
                event_time=at(),
                value=0.25,
            ),
        ),
    }

    first = FactorComputationArtifact.create(
        artifact_id="artifact-computation-001",
        run_id="run-001",
        attempt_id="attempt-001",
        **shared,
    )
    replay = FactorComputationArtifact.create(
        artifact_id="artifact-computation-002",
        run_id="run-002",
        attempt_id="attempt-002",
        **shared,
    )

    assert replay.manifest.content_hash == first.manifest.content_hash
    assert replay.payload() == first.payload()


def test_run_fingerprint_binds_every_execution_identity_field() -> None:
    inputs = {
        "experiment_spec_hash": "1" * 64,
        "factor_ir_hash": "2" * 64,
        "snapshot_id": "snapshot-001",
        "snapshot_manifest_hash": "3" * 64,
        "code_sha": "a" * 40,
        "image_digest": "sha256:" + "4" * 64,
        "dependency_lock_hash": "5" * 64,
        "executor_version": "factor-executor/v1",
        "config_hash": "6" * 64,
        "random_seed": 41,
    }
    baseline = compute_run_fingerprint(**inputs)

    assert len(baseline) == 64
    for field, replacement in (
        ("experiment_spec_hash", "7" * 64),
        ("factor_ir_hash", "7" * 64),
        ("snapshot_id", "snapshot-002"),
        ("snapshot_manifest_hash", "7" * 64),
        ("code_sha", "b" * 40),
        ("image_digest", "sha256:" + "7" * 64),
        ("dependency_lock_hash", "7" * 64),
        ("executor_version", "factor-executor/v2"),
        ("config_hash", "7" * 64),
        ("random_seed", 42),
    ):
        changed = dict(inputs)
        changed[field] = replacement
        assert compute_run_fingerprint(**changed) != baseline


def test_attempt_direct_construction_validates_invariants() -> None:
    with pytest.raises(ValueError, match="ordinal"):
        Attempt(
            attempt_id="attempt-001",
            run_id="run-001",
            ordinal=0,
            state=AttemptState.QUEUED,
            queued_at=at(),
            updated_at=at(),
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        Attempt(
            attempt_id="attempt-001",
            run_id="run-001",
            ordinal=1,
            state=AttemptState.QUEUED,
            queued_at=datetime(2026, 8, 12, 12),
            updated_at=at(),
        )
