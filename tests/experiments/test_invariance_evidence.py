from __future__ import annotations

from datetime import UTC, datetime

from quant_platform.data_gateway import QueryPurpose
from quant_platform.experiment_runtime.repository import (
    _factor_table,
    _factor_table_direct,
    _snapshot,
)
from quant_platform.experiments import ExperimentSpec, ResourceBudget
from quant_platform.factor_ir import compile_factor_ir
from tests.experiment_support import factor_ir, snapshot


def _spec(decision_time: datetime) -> ExperimentSpec:
    compiled = compile_factor_ir(factor_ir())
    return ExperimentSpec.draft(
        experiment_id="experiment-001",
        project_id="local",
        research_job_id="job-001",
        brief_version_id="brief-001",
        brief_content_hash="1" * 64,
        factor_ir_hash=compiled.ir_hash,
        snapshot_id="snapshot-cn-a-001",
        snapshot_manifest_hash="3" * 64,
        market="CN_A",
        universe_ref="universe://csi300-pit/v1",
        frequency="1d",
        decision_time=decision_time,
        decision_clock="T_CLOSE+30m",
        trade_clock="T+1_OPEN",
        settlement_clock=None,
        exchange_scope=(),
        contract_chain_ref=None,
        roll_policy_ref=None,
        validation_policy_ref="policy://cn-a-daily-factor/v1",
        license_purpose=QueryPurpose.RESEARCH,
        allowed_license_tags=frozenset({"licensed-research"}),
        random_seed=41,
        resource_budget=ResourceBudget(
            cpu_seconds=300,
            wall_clock_seconds=600,
            memory_mb=2048,
            max_observations=10_000,
        ),
    ).preregister(actor_id="lead-1", at=decision_time)


def test_direct_table_exposes_future_rows_gateway_filters() -> None:
    frozen_snapshot, _ = _snapshot(snapshot())
    compiled = compile_factor_ir(factor_ir())
    # decision_time 08-05 is before the future row's available_time 08-11,
    # so the gateway must exclude it while the direct builder keeps it.
    spec = _spec(datetime(2026, 8, 5, 16, tzinfo=UTC))

    gated = _factor_table(compiled.canonical_json, frozen_snapshot, spec)
    direct = _factor_table_direct(compiled.canonical_json, frozen_snapshot)

    gated_close = [row.values["close"] for row in gated.rows]
    direct_close = [row.values["close"] for row in direct.rows]

    assert -999999.0 in direct_close
    assert -999999.0 not in gated_close
