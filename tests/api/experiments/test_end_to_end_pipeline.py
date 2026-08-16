"""End-to-end pipeline verification (G17-001).

Runs the full research pipeline in sqlite + in-memory stores without external
Postgres/MinIO: preregister -> run -> validate -> promote (with server-side
evidence cross-check) -> two-person approval -> Alpha Pool -> combination ->
attribution. This closes the gap where promotion and approval were only
exercised against real infrastructure (skipped in CI).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from quant_platform.api.app import create_app
from quant_platform.artifacts import InMemoryArtifactStore
from quant_platform.experiment_runtime import (
    ExecutionIdentity,
    InMemoryFormalSnapshotCatalog,
)
from quant_platform.experiment_runtime.repository import (
    SqlAlchemyExperimentRepository,
)
from quant_platform.portfolio.combination import (
    CombinationSpec,
    FactorSignal,
    mvp_combine,
)
from quant_platform.research.api import ResearchGrant, ResearchPrincipal
from quant_platform.research.models import (
    AlphaPoolFactorModel,
    ApprovalWorkflowModel,
    Base,
)
from quant_platform.research.repository import SqlAlchemyResearchRepository
from quant_platform.validation import (
    FormalLabelSnapshot,
    ForwardReturnLabel,
    ICSign,
    InMemoryLabelSnapshotCatalog,
    InMemoryPromotionPolicyCatalog,
    InMemoryValidationPolicyCatalog,
    LabelSnapshotRow,
    PromotionPolicy,
    ValidationPolicy,
)
from quant_platform.validation.alpha_pool import FactorDirection
from quant_platform.validation.attribution import (
    CostBreakdown,
    build_attribution_report,
)
from tests.experiment_support import (
    at,
    create_frozen_brief,
    headers,
    metadata,
    preregister_command,
    run_command,
    snapshot,
)

EXECUTION_IDENTITY = ExecutionIdentity(
    code_sha="a" * 40,
    image_digest="sha256:" + "b" * 64,
    dependency_lock_hash="c" * 64,
    executor_version="factor-executor/v1",
    config_hash="d" * 64,
)


def approver_provider(token: str) -> ResearchPrincipal | None:
    if token not in ("experimenter", "approver-2"):
        return None
    grants = {
        ResearchGrant(name, "local", market)
        for market in ("CN_A", "CN_COMMODITY_FUTURES")
        for name in (
            "research.jobs.manage",
            "research.experiments.read",
            "research.experiments.preregister",
            "research.experiments.run",
            "research.governance.approve",
        )
    }
    actor_id = "experimenter-1" if token == "experimenter" else "experimenter-2"
    return ResearchPrincipal(actor_id=actor_id, grants=frozenset(grants))


def label_snapshot() -> FormalLabelSnapshot:
    return FormalLabelSnapshot(
        snapshot_id="label-snapshot-cn-a-001",
        label=ForwardReturnLabel(
            label_id="label.cn_a.forward_5d",
            market="CN_A",
            horizon=5,
            field_ref="market.eod.forward_return_5d",
        ),
        rows=(
            LabelSnapshotRow(
                instrument_id="600000.SSE",
                event_time=datetime.fromisoformat(at(2)),
                available_time=datetime.fromisoformat(at(12)),
                value=0.2,
            ),
        ),
    )


def make_stack(
    principal_provider: Callable[[str], ResearchPrincipal | None] = approver_provider,
) -> tuple[TestClient, Engine]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    research = SqlAlchemyResearchRepository(engine)
    policy = ValidationPolicy(
        policy_id="policy://cn-a-daily-factor/v1",
        market="CN_A",
        min_coverage=0.0,
        min_observations=1,
        max_constant_ratio=1.0,
        ic_sign=ICSign.ANY,
        min_icir=0.0,
        min_nw_t=0.0,
        quantile_count=2,
        decay_horizons=(5,),
    )
    experiments = SqlAlchemyExperimentRepository(
        engine,
        research_repository=research,
        artifact_store=InMemoryArtifactStore(),
        snapshot_catalog=InMemoryFormalSnapshotCatalog((snapshot(),)),
        execution_identity=EXECUTION_IDENTITY,
        policy_catalog=InMemoryValidationPolicyCatalog((policy,)),
        label_snapshot_catalog=InMemoryLabelSnapshotCatalog((label_snapshot(),)),
        promotion_policy_catalog=InMemoryPromotionPolicyCatalog(
            (
                PromotionPolicy(
                    policy_id="policy://cn-a-promotion/v1",
                    market="CN_A",
                    min_coverage=0.0,
                    min_observations=1,
                    min_oos_ic=0.0,
                    fdr_bound=1.0,
                    min_capacity=0.0,
                ),
            )
        ),
    )
    client = TestClient(
        create_app(
            readiness_probe=lambda: {"postgres": True, "minio": True},
            research_repository=research,
            experiment_repository=experiments,
            research_principal_provider=principal_provider,
        )
    )
    return client, engine


def test_full_research_pipeline() -> None:
    client, engine = make_stack()
    with client:
        job_id, brief_id = create_frozen_brief(client)

        # 1. Preregister a deterministic factor experiment.
        registered = client.post(
            "/v1/experiments:preregister",
            headers=headers("e2e-preregister-0001"),
            json=preregister_command(job_id, brief_id),
        )
        assert registered.status_code == 202
        experiment_id = registered.json()["resource_id"]

        # 2. Run it (invariance evidence must pass).
        run = client.post(
            f"/v1/experiments/{experiment_id}:run",
            headers=headers("e2e-run-command-0001", '"1"'),
            json=run_command(),
        )
        assert run.status_code == 202
        run_id = run.json()["resource_id"]

        # 3. Validate against the label snapshot.
        label = label_snapshot()
        validated = client.post(
            f"/v1/experiment-runs/{run_id}:validate",
            headers=headers("e2e-validate-0001"),
            json={
                "metadata": metadata("Validate factor"),
                "policy_id": "policy://cn-a-daily-factor/v1",
                "label_snapshot_id": label.snapshot_id,
                "label_snapshot_manifest_hash": label.content_hash(),
            },
        )
        assert validated.status_code == 202

        report = client.get(
            f"/v1/experiment-runs/{run_id}/validation", headers=headers()
        ).json()
        quality = report["data_quality"]
        coverage = quality["coverage_ratio"]
        observations = quality["observation_count"]

        # 4. Promote with evidence that matches the stored report.
        promoted = client.post(
            f"/v1/experiment-runs/{run_id}:promote",
            headers=headers("e2e-promote-0001"),
            json={
                "metadata": metadata("Promote factor"),
                "policy_id": "policy://cn-a-promotion/v1",
                "direction": "LONG_SHORT",
                "universe": "cn-a-000300",
                "horizon": 5,
                "risk_premium": False,
                "evidence": {
                    "coverage": coverage,
                    "observations": observations,
                    "oos_ic": 0.05,
                    "expected_direction": "POSITIVE",
                    "fdr_qvalue": 0.03,
                    "capacity_aum": 1_000_000.0,
                    "sharpe": 1.0,
                    "effect_score": 0.8,
                    "stability_score": 0.7,
                    "independence_score": 0.9,
                    "cost_value_score": 0.6,
                    "interpretability_score": 0.5,
                },
            },
        )
        assert promoted.status_code == 202

        # 5. Promotion requires two-person approval; the factor is pending.
        with Session(engine) as session:
            workflow = session.scalar(select(ApprovalWorkflowModel))
            assert workflow is not None
            alpha_pending = session.scalar(select(AlphaPoolFactorModel))
            assert alpha_pending is not None
            assert alpha_pending.lifecycle_state == "PENDING_APPROVAL"
            workflow_id = workflow.workflow_id

        first_sign = client.post(
            f"/v1/approvals/{workflow_id}:sign",
            headers=headers(),
            json={"decision": "APPROVE", "reason": "reviewed"},
        )
        assert first_sign.status_code == 202
        assert first_sign.json()["state"] == "PENDING"

        second_sign = client.post(
            f"/v1/approvals/{workflow_id}:sign",
            headers={"Authorization": "Bearer approver-2"},
            json={"decision": "APPROVE", "reason": "second reviewer"},
        )
        assert second_sign.status_code == 202
        assert second_sign.json()["state"] == "APPROVED"

        # 6. The factor is now promoted into the Alpha Pool.
        with Session(engine) as session:
            alpha = session.scalar(select(AlphaPoolFactorModel))
            assert alpha is not None
            assert alpha.lifecycle_state == "PROMOTED"
            factor_hash = alpha.factor_ir_hash

        # 7. The promoted factor feeds combination and attribution.
        combined = mvp_combine(
            (
                FactorSignal(
                    factor_ir_hash=factor_hash,
                    train_ic=0.05,
                    ic_vol=0.08,
                    direction=FactorDirection.LONG_SHORT,
                ),
            ),
            CombinationSpec(spec_id="spec://e2e/v1"),
        )
        assert combined.entries

        attribution = build_attribution_report(
            start_nav=Decimal("100000"),
            gross_pnl=Decimal("100"),
            cost_breakdown=CostBreakdown(
                commission=Decimal("0"),
                stamp_duty=Decimal("0"),
                slippage=Decimal("0"),
                impact=Decimal("0"),
            ),
            risk_exposures=((factor_hash, 0.4),),
            capacity_utilization=0.05,
            unfillable_count=0,
            total_orders=1,
        )
        assert attribution.content_hash()


def test_promote_rejects_inflated_evidence() -> None:
    client, _ = make_stack()
    with client:
        job_id, brief_id = create_frozen_brief(client)
        registered = client.post(
            "/v1/experiments:preregister",
            headers=headers("e2e-inflate-preregister-0001"),
            json=preregister_command(job_id, brief_id),
        )
        experiment_id = registered.json()["resource_id"]
        run = client.post(
            f"/v1/experiments/{experiment_id}:run",
            headers=headers("e2e-inflate-run-0001", '"1"'),
            json=run_command(),
        )
        run_id = run.json()["resource_id"]
        label = label_snapshot()
        client.post(
            f"/v1/experiment-runs/{run_id}:validate",
            headers=headers("e2e-inflate-validate-0001"),
            json={
                "metadata": metadata("Validate factor"),
                "policy_id": "policy://cn-a-daily-factor/v1",
                "label_snapshot_id": label.snapshot_id,
                "label_snapshot_manifest_hash": label.content_hash(),
            },
        )

        promoted = client.post(
            f"/v1/experiment-runs/{run_id}:promote",
            headers=headers("e2e-inflate-promote-0001"),
            json={
                "metadata": metadata("Promote with inflated evidence"),
                "policy_id": "policy://cn-a-promotion/v1",
                "direction": "LONG_SHORT",
                "universe": "cn-a-000300",
                "horizon": 5,
                "risk_premium": False,
                "evidence": {
                    "coverage": 0.99,  # inflated: does not match the stored report
                    "observations": 99_999,
                    "oos_ic": 0.05,
                    "expected_direction": "POSITIVE",
                    "fdr_qvalue": 0.03,
                    "capacity_aum": 1_000_000.0,
                    "sharpe": 1.0,
                    "effect_score": 0.8,
                    "stability_score": 0.7,
                    "independence_score": 0.9,
                    "cost_value_score": 0.6,
                    "interpretability_score": 0.5,
                },
            },
        )

        assert promoted.status_code == 422
        assert "EVIDENCE_MISMATCH" in promoted.json()["code"]
