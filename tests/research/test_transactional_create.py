from typing import Any, Never

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.pool import StaticPool

from quant_platform.research.models import (
    AuditEventModel,
    Base,
    OutboxEventModel,
    ResearchBriefVersionModel,
    ResearchCommandReceiptModel,
    ResearchJobModel,
)
from quant_platform.research.repository import SqlAlchemyResearchRepository
from quant_platform.research.schemas import BriefContent


def create_repository(
    *, fail_before_commit: bool = False
) -> tuple[Engine, SqlAlchemyResearchRepository]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def failure() -> Never:
        raise RuntimeError("injected transaction failure")

    repository = SqlAlchemyResearchRepository(
        engine,
        before_commit=failure if fail_before_commit else None,
    )
    return engine, repository


def command_arguments() -> dict[str, Any]:
    return {
        "actor_id": "researcher-1",
        "project_id": "local",
        "idempotency_key": "create-job-atomic-0001",
        "request_hash": "sha256:request",
        "reason": "Create a preregistered research workspace",
        "parent_artifact_id": None,
        "title": "CN_A 20TD research",
        "market": "CN_A",
        "universe_ref": "universe://csi500/pit",
        "frequency": "1d",
        "decision_clock": "T_CLOSE",
        "trade_clock": "T_PLUS_1_OPEN",
        "settlement_clock": None,
        "exchange_scope": [],
        "contract_selection": None,
        "roll_policy": None,
        "horizon": "20TD",
        "research_brief_version_id": "brief://seed",
        "budget": {"candidate_limit": 10},
    }


def table_count(engine: Engine, model: type[Any]) -> int:
    with engine.connect() as connection:
        return int(connection.scalar(select(func.count()).select_from(model)) or 0)


def test_create_job_command_commits_domain_receipt_audit_and_outbox_once() -> None:
    engine, repository = create_repository()

    first = repository.execute_create_job_command(**command_arguments())
    replay = repository.execute_create_job_command(**command_arguments())

    assert replay == first
    assert table_count(engine, ResearchJobModel) == 1
    assert table_count(engine, ResearchCommandReceiptModel) == 1
    assert table_count(engine, AuditEventModel) == 1
    assert table_count(engine, OutboxEventModel) == 1


def test_create_job_command_rolls_back_every_record_on_failure() -> None:
    engine, repository = create_repository(fail_before_commit=True)

    with pytest.raises(RuntimeError, match="injected transaction failure"):
        repository.execute_create_job_command(**command_arguments())

    assert table_count(engine, ResearchJobModel) == 0
    assert table_count(engine, ResearchCommandReceiptModel) == 0
    assert table_count(engine, AuditEventModel) == 0
    assert table_count(engine, OutboxEventModel) == 0


def test_brief_commands_commit_receipt_audit_and_outbox_once() -> None:
    engine, repository = create_repository()
    job = repository.create_job(
        actor_id="researcher-1",
        project_id="local",
        title="Inventory signal",
        market="CN_A",
        universe_ref="universe://csi500/pit",
        frequency="1d",
        decision_clock="T_CLOSE",
        trade_clock="T_PLUS_1_OPEN",
        settlement_clock=None,
        exchange_scope=[],
        contract_selection=None,
        roll_policy=None,
        horizon="20TD",
        research_brief_version_id="brief://seed",
        budget={"candidate_limit": 10},
    )
    content = {
        "hypothesis": "Inventory pressure predicts returns",
        "economic_mechanism": "Scarcity affects marginal pricing.",
        "expected_direction": "NEGATIVE",
        "falsification_conditions": ["No OOS contribution"],
        "allowed_data_domains": ["formal.market.eod"],
        "forbidden_data_domains": ["future.revisions"],
        "constraints": ["daily only"],
        "evidence_ref_ids": [],
        "uncertainties": ["publication lag"],
    }

    def execute() -> object:
        return repository.execute_create_brief_command(
            job_id=job.id,
            actor_id="researcher-1",
            idempotency_key="create-brief-atomic-0001",
            request_hash="sha256:create-brief",
            reason="Create a preregistered brief",
            parent_artifact_id=None,
            content=content,
            expected_job_version=1,
        )

    first = execute()
    replay = execute()

    assert replay == first
    assert table_count(engine, ResearchBriefVersionModel) == 1
    assert table_count(engine, ResearchCommandReceiptModel) == 1
    assert table_count(engine, AuditEventModel) == 1
    assert table_count(engine, OutboxEventModel) == 1


def test_brief_command_failure_rolls_back_domain_receipt_audit_and_outbox() -> None:
    engine, base = create_repository()
    job = base.create_job(
        actor_id="researcher-1",
        project_id="local",
        title="Inventory signal",
        market="CN_A",
        universe_ref="universe://csi500/pit",
        frequency="1d",
        decision_clock="T_CLOSE",
        trade_clock="T_PLUS_1_OPEN",
        settlement_clock=None,
        exchange_scope=[],
        contract_selection=None,
        roll_policy=None,
        horizon="20TD",
        research_brief_version_id="brief://seed",
        budget={"candidate_limit": 10},
    )

    def failure() -> Never:
        raise RuntimeError("injected transaction failure")

    repository = SqlAlchemyResearchRepository(engine, before_commit=failure)
    with pytest.raises(RuntimeError, match="injected transaction failure"):
        repository.execute_create_brief_command(
            job_id=job.id,
            actor_id="researcher-1",
            idempotency_key="create-brief-rollback-01",
            request_hash="sha256:create-brief-failure",
            reason="Create a preregistered brief",
            parent_artifact_id=None,
            content={
                "hypothesis": "Inventory pressure predicts returns",
                "economic_mechanism": "Scarcity affects marginal pricing.",
                "expected_direction": "NEGATIVE",
                "falsification_conditions": ["No OOS contribution"],
                "allowed_data_domains": ["formal.market.eod"],
                "forbidden_data_domains": [],
                "constraints": ["daily only"],
                "evidence_ref_ids": [],
                "uncertainties": [],
            },
            expected_job_version=1,
        )

    assert table_count(engine, ResearchBriefVersionModel) == 0
    assert table_count(engine, ResearchCommandReceiptModel) == 0
    assert table_count(engine, AuditEventModel) == 0
    assert table_count(engine, OutboxEventModel) == 0


def test_update_and_freeze_commands_are_atomic_and_replayable() -> None:
    engine, repository = create_repository()
    job = repository.create_job(
        actor_id="researcher-1",
        project_id="local",
        title="Inventory signal",
        market="CN_A",
        universe_ref="universe://csi500/pit",
        frequency="1d",
        decision_clock="T_CLOSE",
        trade_clock="T_PLUS_1_OPEN",
        settlement_clock=None,
        exchange_scope=[],
        contract_selection=None,
        roll_policy=None,
        horizon="20TD",
        research_brief_version_id="brief://seed",
        budget={"candidate_limit": 10},
    )
    content = {
        "hypothesis": "Inventory pressure predicts returns",
        "economic_mechanism": "Scarcity affects marginal pricing.",
        "expected_direction": "NEGATIVE",
        "falsification_conditions": ["No OOS contribution"],
        "allowed_data_domains": ["formal.market.eod"],
        "forbidden_data_domains": ["future.revisions"],
        "constraints": ["daily only"],
        "evidence_ref_ids": ["evidence://inventory/1"],
        "uncertainties": ["publication lag"],
    }
    created = repository.execute_create_brief_command(
        job_id=job.id,
        actor_id="researcher-1",
        idempotency_key="brief-lifecycle-create-01",
        request_hash="sha256:create",
        reason="Create brief",
        parent_artifact_id=None,
        content=content,
        expected_job_version=1,
    )
    updated_content = {**content, "hypothesis": "Revised inventory hypothesis"}
    updated = repository.execute_update_brief_command(
        brief_id=created.resource_id,
        actor_id="researcher-1",
        idempotency_key="brief-lifecycle-update-01",
        request_hash="sha256:update",
        reason="Update brief",
        parent_artifact_id=None,
        content=BriefContent.model_validate(updated_content),
        expected_resource_version=1,
    )
    update_replay = repository.execute_update_brief_command(
        brief_id=created.resource_id,
        actor_id="researcher-1",
        idempotency_key="brief-lifecycle-update-01",
        request_hash="sha256:update",
        reason="Update brief",
        parent_artifact_id=None,
        content=BriefContent.model_validate(updated_content),
        expected_resource_version=1,
    )
    frozen = repository.execute_freeze_brief_command(
        brief_id=created.resource_id,
        actor_id="researcher-1",
        idempotency_key="brief-lifecycle-freeze-01",
        request_hash="sha256:freeze",
        reason="Freeze brief",
        parent_artifact_id=None,
        expected_resource_version=2,
    )
    freeze_replay = repository.execute_freeze_brief_command(
        brief_id=created.resource_id,
        actor_id="researcher-1",
        idempotency_key="brief-lifecycle-freeze-01",
        request_hash="sha256:freeze",
        reason="Freeze brief",
        parent_artifact_id=None,
        expected_resource_version=2,
    )
    snapshot = repository.get_brief(created.resource_id)

    assert update_replay == updated
    assert freeze_replay == frozen
    assert snapshot is not None
    assert snapshot.status.value == "FROZEN"
    assert snapshot.resource_version == 3
    assert snapshot.content_hash is not None
    assert table_count(engine, ResearchCommandReceiptModel) == 3
    assert table_count(engine, AuditEventModel) == 3
    assert table_count(engine, OutboxEventModel) == 3
