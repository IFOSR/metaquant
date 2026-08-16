from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from quant_platform.data_gateway import (
    ArtifactClass,
    DatasetContract,
    FieldContract,
    FrozenSnapshot,
    QueryPurpose,
    SourceClass,
)
from quant_platform.experiments import (
    ExperimentSpec,
    FormalPreconditionError,
    FormalSnapshotBinding,
    ResourceBudget,
    validate_formal_preconditions,
)
from quant_platform.factor_ir import compile_factor_ir
from quant_platform.research.schemas import (
    BriefDirection,
    BriefStatus,
    MarketId,
    ResearchBriefRecord,
    ResearchJobRecord,
    ResearchJobState,
)


def at(hour: int = 0) -> datetime:
    return datetime(2026, 8, 12, hour, tzinfo=UTC)


def factor_payload() -> dict[str, object]:
    return {
        "schema_version": "factor-ir/v1",
        "factor_id": "price.momentum_20d",
        "version": "1.0.0",
        "market_scope": {
            "market": "CN_A",
            "frequency": "1d",
            "universe_ref": "universe://csi300-pit/v1",
        },
        "decision_clock": {
            "signal_time": "T_CLOSE+30m",
            "earliest_trade_time": "T+1_OPEN",
        },
        "inputs": [
            {
                "alias": "close",
                "field_ref": "market.eod.close_adjusted",
                "data_type": "ScalarSeries",
                "unit": "CNY",
                "available_time_rule": "T_CLOSE+20m",
            }
        ],
        "expression": {
            "op": "returns",
            "args": [{"ref": "close"}],
            "params": {"periods": 20},
        },
        "validation_policy_ref": "policy://cn-a-daily-factor/v1",
    }


def job() -> ResearchJobRecord:
    return ResearchJobRecord(
        id="job-001",
        project_id="local",
        resource_version=2,
        title="Momentum experiment",
        market=MarketId.CN_A,
        environment="RESEARCH",
        state=ResearchJobState.READY,
        owner="researcher-1",
        universe_ref="universe://csi300-pit/v1",
        frequency="1d",
        decision_clock="T_CLOSE+30m",
        trade_clock="T+1_OPEN",
        settlement_clock=None,
        exchange_scope=[],
        contract_selection=None,
        roll_policy=None,
        horizon="20TD",
        research_brief_version_id="brief-001",
        budget={"candidate_limit": 10, "wall_clock_minutes": 30},
        created_at=at(),
        updated_at=at(),
    )


def brief(*, status: BriefStatus = BriefStatus.FROZEN) -> ResearchBriefRecord:
    return ResearchBriefRecord(
        id="brief-001",
        job_id="job-001",
        version=1,
        resource_version=2,
        status=status,
        hypothesis="Past medium-term returns persist.",
        economic_mechanism="Slow information diffusion.",
        expected_direction=BriefDirection.POSITIVE,
        falsification_conditions=["No stable coverage"],
        allowed_data_domains=["formal.market.eod"],
        forbidden_data_domains=["future.revisions"],
        constraints=["daily only"],
        evidence_ref_ids=["evidence://momentum/1"],
        uncertainties=["corporate action lag"],
        content_hash="1" * 64 if status is BriefStatus.FROZEN else None,
        created_at=at(),
        created_by="researcher-1",
        frozen_at=at(1) if status is BriefStatus.FROZEN else None,
        frozen_by="lead-1" if status is BriefStatus.FROZEN else None,
    )


def snapshot(
    *,
    artifact_class: ArtifactClass = ArtifactClass.FORMAL,
    source_class: SourceClass = SourceClass.FORMAL,
    purposes: frozenset[QueryPurpose] = frozenset({QueryPurpose.RESEARCH}),
) -> FrozenSnapshot:
    return FrozenSnapshot.create(
        snapshot_id="snapshot-001",
        frozen_at=at(2),
        contracts=(
            DatasetContract(
                dataset_id="market-eod",
                source_id="licensed-source",
                source_class=source_class,
                fields=(
                    FieldContract(
                        name="market.eod.close_adjusted",
                        value_type="decimal",
                        unit="CNY",
                        license_tag="licensed-research",
                        allowed_purposes=purposes,
                    ),
                ),
            ),
        ),
        rows=(),
        artifact_class=artifact_class,
    )


def snapshot_binding(**changes: object) -> FormalSnapshotBinding:
    values: dict[str, object] = {
        "snapshot_id": "snapshot-001",
        "snapshot_manifest_hash": "3" * 64,
        "sealed": True,
        "artifact_class": ArtifactClass.FORMAL,
        "market": "CN_A",
        "universe_ref": "universe://csi300-pit/v1",
        "frequency": "1d",
        "decision_clock": "T_CLOSE+30m",
        "trade_clock": "T+1_OPEN",
        "settlement_clock": None,
        "exchange_scope": (),
        "contract_chain_ref": None,
        "roll_policy_ref": None,
        "purpose": QueryPurpose.RESEARCH,
        "allowed_license_tags": frozenset({"licensed-research"}),
    }
    values.update(changes)
    return FormalSnapshotBinding(**cast(Any, values))


def registered_spec(**changes: object) -> ExperimentSpec:
    compiled = compile_factor_ir(factor_payload())
    values: dict[str, object] = {
        "experiment_id": "experiment-001",
        "project_id": "local",
        "research_job_id": "job-001",
        "brief_version_id": "brief-001",
        "brief_content_hash": "1" * 64,
        "factor_ir_hash": compiled.ir_hash,
        "snapshot_id": "snapshot-001",
        "snapshot_manifest_hash": "3" * 64,
        "market": "CN_A",
        "universe_ref": "universe://csi300-pit/v1",
        "frequency": "1d",
        "decision_time": at(),
        "decision_clock": "T_CLOSE+30m",
        "trade_clock": "T+1_OPEN",
        "settlement_clock": None,
        "exchange_scope": (),
        "contract_chain_ref": None,
        "roll_policy_ref": None,
        "validation_policy_ref": "policy://cn-a-daily-factor/v1",
        "license_purpose": QueryPurpose.RESEARCH,
        "allowed_license_tags": frozenset({"licensed-research"}),
        "random_seed": 41,
        "resource_budget": ResourceBudget(
            cpu_seconds=300,
            wall_clock_seconds=600,
            memory_mb=2048,
            max_observations=1_000_000,
        ),
    }
    values.update(changes)
    return ExperimentSpec.draft(**values).preregister(
        actor_id="lead-1",
        at=at(3),
    )


def validate(
    *,
    spec: ExperimentSpec | None = None,
    research_job: ResearchJobRecord | None = None,
    research_brief: ResearchBriefRecord | None = None,
    frozen_snapshot: FrozenSnapshot | None = None,
    binding: FormalSnapshotBinding | None = None,
) -> None:
    validate_formal_preconditions(
        spec=spec or registered_spec(),
        research_job=research_job or job(),
        research_brief=research_brief or brief(),
        frozen_snapshot=frozen_snapshot or snapshot(),
        snapshot_binding=binding or snapshot_binding(),
        compiled_ir=compile_factor_ir(factor_payload()),
    )


def assert_blocked(code: str, **kwargs: object) -> None:
    with pytest.raises(FormalPreconditionError) as caught:
        validate(**kwargs)  # type: ignore[arg-type]
    assert code in {item.code for item in caught.value.violations}


def test_valid_formal_bindings_pass_and_return_immutable_identity() -> None:
    result = validate_formal_preconditions(
        spec=registered_spec(),
        research_job=job(),
        research_brief=brief(),
        frozen_snapshot=snapshot(),
        snapshot_binding=snapshot_binding(),
        compiled_ir=compile_factor_ir(factor_payload()),
    )

    assert result.market == "CN_A"
    assert result.frequency == "1d"
    assert result.snapshot_id == "snapshot-001"
    assert result.factor_ir_hash == compile_factor_ir(factor_payload()).ir_hash


def test_mutable_brief_and_unregistered_spec_fail_closed() -> None:
    assert_blocked("BRIEF_NOT_FROZEN", research_brief=brief(status=BriefStatus.DRAFT))
    assert_blocked(
        "SPEC_NOT_PREREGISTERED",
        spec=registered_spec().close(actor_id="lead-1", at=at(4)),
    )


@pytest.mark.parametrize(
    ("code", "binding"),
    [
        ("SNAPSHOT_NOT_EXPLICIT", snapshot_binding(snapshot_id="latest")),
        ("SNAPSHOT_NOT_SEALED", snapshot_binding(sealed=False)),
        (
            "SNAPSHOT_NOT_FORMAL",
            snapshot_binding(artifact_class=ArtifactClass.EXPLORATORY),
        ),
        ("MARKET_MISMATCH", snapshot_binding(market="CN_COMMODITY_FUTURES")),
        ("UNIVERSE_MISMATCH", snapshot_binding(universe_ref="universe://other/v1")),
        ("FREQUENCY_MISMATCH", snapshot_binding(frequency="5m")),
        ("CLOCK_MISMATCH", snapshot_binding(decision_clock="T_OPEN")),
        (
            "LICENSE_PURPOSE_MISMATCH",
            snapshot_binding(purpose=QueryPurpose.REPORT),
        ),
    ],
)
def test_snapshot_binding_mismatches_fail_closed(
    code: str,
    binding: FormalSnapshotBinding,
) -> None:
    assert_blocked(code, binding=binding)


def test_exploratory_snapshot_source_and_unlicensed_field_fail_closed() -> None:
    assert_blocked(
        "SNAPSHOT_NOT_FORMAL",
        frozen_snapshot=snapshot(artifact_class=ArtifactClass.EXPLORATORY),
    )
    assert_blocked(
        "DATASET_SOURCE_NOT_FORMAL",
        frozen_snapshot=snapshot(source_class=SourceClass.EXPLORATORY),
    )
    assert_blocked(
        "FIELD_PURPOSE_NOT_ALLOWED",
        frozen_snapshot=snapshot(purposes=frozenset({QueryPurpose.REPORT})),
    )
    assert_blocked(
        "FIELD_LICENSE_NOT_ALLOWED",
        spec=registered_spec(allowed_license_tags=frozenset({"wrong-license"})),
    )


def test_market_universe_policy_clock_and_ir_hash_mismatches_fail_closed() -> None:
    assert_blocked(
        "MARKET_MISMATCH",
        spec=registered_spec(
            market="CN_COMMODITY_FUTURES",
            settlement_clock="T_SETTLEMENT",
            exchange_scope=("SHFE",),
            contract_chain_ref="contract-chain://actual/v1",
            roll_policy_ref="roll-policy://oi-3d/v1",
        ),
    )
    assert_blocked(
        "UNIVERSE_MISMATCH",
        spec=registered_spec(universe_ref="universe://other/v1"),
    )
    assert_blocked(
        "VALIDATION_POLICY_MISMATCH",
        spec=registered_spec(validation_policy_ref="policy://other/v1"),
    )
    assert_blocked(
        "CLOCK_MISMATCH",
        spec=registered_spec(decision_clock="T_OPEN"),
    )
    assert_blocked(
        "FACTOR_IR_HASH_MISMATCH", spec=registered_spec(factor_ir_hash="9" * 64)
    )


def test_project_environment_brief_and_snapshot_identity_fail_closed() -> None:
    assert_blocked("PROJECT_NOT_FORMAL", spec=registered_spec(project_id="other"))
    assert_blocked(
        "BRIEF_ID_MISMATCH",
        spec=registered_spec(brief_version_id="brief-other"),
    )
    assert_blocked(
        "BRIEF_HASH_MISMATCH",
        spec=registered_spec(brief_content_hash="9" * 64),
    )
    assert_blocked(
        "SNAPSHOT_ID_MISMATCH",
        spec=registered_spec(snapshot_id="snapshot-other"),
    )
    assert_blocked(
        "SNAPSHOT_MANIFEST_HASH_MISMATCH",
        spec=registered_spec(snapshot_manifest_hash="9" * 64),
    )


def test_missing_factor_field_fails_closed() -> None:
    empty_contract_snapshot = FrozenSnapshot.create(
        snapshot_id="snapshot-001",
        frozen_at=at(2),
        contracts=(
            DatasetContract(
                dataset_id="other",
                source_id="licensed-source",
                source_class=SourceClass.FORMAL,
                fields=(
                    FieldContract(
                        name="market.eod.volume",
                        value_type="decimal",
                        unit="SHARE",
                        license_tag="licensed-research",
                        allowed_purposes=frozenset({QueryPurpose.RESEARCH}),
                    ),
                ),
            ),
        ),
        rows=(),
        artifact_class=ArtifactClass.FORMAL,
    )

    assert_blocked("IR_FIELD_NOT_IN_SNAPSHOT", frozen_snapshot=empty_contract_snapshot)


def test_commodity_futures_require_full_market_scope() -> None:
    futures_payload = factor_payload()
    futures_payload["market_scope"] = {
        "market": "CN_COMMODITY_FUTURES",
        "frequency": "1d",
        "universe_ref": "universe://cn-futures-actual/v1",
        "exchange_scope": ["SHFE"],
        "contract_chain_ref": "contract-chain://actual/v1",
        "roll_policy_ref": "roll-policy://oi-3d/v1",
    }
    futures_payload["decision_clock"] = {
        "signal_time": "T_CLOSE+30m",
        "earliest_trade_time": "T+1_OPEN",
    }
    compiled = compile_factor_ir(futures_payload)
    with pytest.raises(ValueError, match="settlement_clock"):
        registered_spec(
            factor_ir_hash=compiled.ir_hash,
            market="CN_COMMODITY_FUTURES",
            universe_ref="universe://cn-futures-actual/v1",
            settlement_clock=None,
            exchange_scope=("SHFE",),
            contract_chain_ref="contract-chain://actual/v1",
            roll_policy_ref="roll-policy://oi-3d/v1",
        )


def test_commodity_futures_scope_fields_fail_closed_on_mismatch() -> None:
    futures_payload = factor_payload()
    futures_payload["market_scope"] = {
        "market": "CN_COMMODITY_FUTURES",
        "frequency": "1d",
        "universe_ref": "universe://cn-futures-actual/v1",
        "exchange_scope": ["SHFE"],
        "contract_chain_ref": "contract-chain://actual/v1",
        "roll_policy_ref": "roll-policy://oi-3d/v1",
    }
    compiled = compile_factor_ir(futures_payload)

    futures_spec = registered_spec(
        factor_ir_hash=compiled.ir_hash,
        market="CN_COMMODITY_FUTURES",
        universe_ref="universe://cn-futures-actual/v1",
        settlement_clock="T+1_OPEN",
        exchange_scope=("SHFE",),
        contract_chain_ref="contract-chain://actual/v1",
        roll_policy_ref="roll-policy://oi-3d/v1",
    )
    futures_job = ResearchJobRecord(
        id="job-001",
        project_id="local",
        resource_version=2,
        title="Futures momentum",
        market=MarketId.CN_COMMODITY_FUTURES,
        environment="RESEARCH",
        state=ResearchJobState.READY,
        owner="researcher-1",
        universe_ref="universe://cn-futures-actual/v1",
        frequency="1d",
        decision_clock="T_CLOSE+30m",
        trade_clock="T+1_OPEN",
        settlement_clock="T+1_OPEN",
        exchange_scope=["SHFE"],
        contract_selection="ACTUAL_CONTRACTS_ONLY",
        roll_policy="roll-policy://oi-3d/v1",
        horizon="20TD",
        research_brief_version_id="brief-001",
        budget={"candidate_limit": 10, "wall_clock_minutes": 30},
        created_at=at(),
        updated_at=at(),
    )

    def futures_binding(**changes: object) -> FormalSnapshotBinding:
        values = {
            "snapshot_id": "snapshot-001",
            "snapshot_manifest_hash": "3" * 64,
            "sealed": True,
            "artifact_class": ArtifactClass.FORMAL,
            "market": "CN_COMMODITY_FUTURES",
            "universe_ref": "universe://cn-futures-actual/v1",
            "frequency": "1d",
            "decision_clock": "T_CLOSE+30m",
            "trade_clock": "T+1_OPEN",
            "settlement_clock": "T+1_OPEN",
            "exchange_scope": ("SHFE",),
            "contract_chain_ref": "contract-chain://actual/v1",
            "roll_policy_ref": "roll-policy://oi-3d/v1",
            "purpose": QueryPurpose.RESEARCH,
            "allowed_license_tags": frozenset({"licensed-research"}),
        }
        values.update(changes)
        return FormalSnapshotBinding(**cast(Any, values))

    validate_formal_preconditions(
        spec=futures_spec,
        research_job=futures_job,
        research_brief=brief(),
        frozen_snapshot=snapshot(),
        snapshot_binding=futures_binding(),
        compiled_ir=compiled,
    )

    with pytest.raises(FormalPreconditionError) as caught:
        validate_formal_preconditions(
            spec=futures_spec,
            research_job=futures_job,
            research_brief=brief(),
            frozen_snapshot=snapshot(),
            snapshot_binding=futures_binding(exchange_scope=("DCE",)),
            compiled_ir=compiled,
        )
    assert "EXCHANGE_SCOPE_MISMATCH" in {item.code for item in caught.value.violations}
