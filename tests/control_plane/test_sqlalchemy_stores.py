from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from quant_platform.control_plane import (
    AuditEvent,
    OutboxEnvelope,
    ProblemError,
    SqlAlchemyAuditStore,
    SqlAlchemyConsumerDeduplicator,
    SqlAlchemyIdempotencyStore,
    SqlAlchemyOutboxStore,
)
from quant_platform.research.models import AuditEventModel, Base, ConsumerReceiptModel

NOW = datetime(2026, 8, 12, tzinfo=UTC)


@pytest.fixture
def engine() -> Engine:
    database = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(database)
    return database


def audit_event() -> AuditEvent:
    return AuditEvent(
        id="audit-1",
        occurred_at=NOW,
        actor="researcher-1",
        action="research_job.created",
        resource_id="job-1",
        resource_version="1",
        reason="Create a preregistered research workspace",
        request_id="cmd-1",
        after_hash="sha256:job-1",
    )


def outbox_event() -> OutboxEnvelope:
    return OutboxEnvelope(
        event_id="event-1",
        event_type="ResearchJobCreated",
        aggregate_type="ResearchJob",
        aggregate_id="job-1",
        aggregate_version="1",
        occurred_at=NOW,
        payload={"state": "DRAFT"},
    )


def test_sqlalchemy_audit_store_is_append_only(engine: Engine) -> None:
    store = SqlAlchemyAuditStore(engine)

    store.append(audit_event())

    assert store.list() == (audit_event(),)
    with pytest.raises(ValueError, match="audit event already exists"):
        store.append(audit_event())


def test_sqlalchemy_outbox_tracks_pending_and_published_events(
    engine: Engine,
) -> None:
    store = SqlAlchemyOutboxStore(engine)

    store.append(outbox_event())
    assert store.pending() == (outbox_event(),)

    store.mark_published("event-1")
    assert store.pending() == ()


def test_sqlalchemy_consumer_deduplicator_commits_effect_and_receipt_together(
    engine: Engine,
) -> None:
    first = SqlAlchemyConsumerDeduplicator(engine, consumer_id="report-projector")
    second = SqlAlchemyConsumerDeduplicator(engine, consumer_id="metrics-projector")

    def append_audit(session: Session) -> None:
        session.add(AuditEventModel(**audit_event().model_dump()))

    assert first.execute(outbox_event(), append_audit) is True
    assert first.execute(outbox_event(), append_audit) is False
    assert second.execute(outbox_event(), lambda _session: None) is True

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEventModel)) == 1
        assert (
            session.scalar(select(func.count()).select_from(ConsumerReceiptModel)) == 2
        )


def test_sqlalchemy_consumer_deduplicator_rolls_back_receipt_and_retries_after_crash(
    engine: Engine,
) -> None:
    deduplicator = SqlAlchemyConsumerDeduplicator(
        engine, consumer_id="report-projector"
    )
    attempts = 0

    def crash_after_effect(session: Session) -> None:
        nonlocal attempts
        attempts += 1
        session.add(AuditEventModel(**audit_event().model_dump()))
        if attempts == 1:
            raise RuntimeError("projector crashed")

    with pytest.raises(RuntimeError, match="projector crashed"):
        deduplicator.execute(outbox_event(), crash_after_effect)

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEventModel)) == 0
        assert (
            session.scalar(select(func.count()).select_from(ConsumerReceiptModel)) == 0
        )

    assert deduplicator.execute(outbox_event(), crash_after_effect) is True
    assert attempts == 2


def test_sqlalchemy_consumer_claim_refuses_to_mark_unprocessed_event(
    engine: Engine,
) -> None:
    deduplicator = SqlAlchemyConsumerDeduplicator(
        engine, consumer_id="report-projector"
    )

    with pytest.raises(RuntimeError, match="does not represent processed"):
        deduplicator.claim(outbox_event())

    with Session(engine) as session:
        assert (
            session.scalar(select(func.count()).select_from(ConsumerReceiptModel)) == 0
        )


def test_sqlalchemy_idempotency_store_replays_and_rejects_conflicts(
    engine: Engine,
) -> None:
    executions = 0
    store: SqlAlchemyIdempotencyStore[dict[str, str]] = SqlAlchemyIdempotencyStore(
        engine, namespace="research"
    )

    def operation() -> dict[str, str]:
        nonlocal executions
        executions += 1
        return {"command_id": "cmd-1"}

    first = store.execute("idempotency-key-0001", "sha256:a", operation)
    replay = store.execute("idempotency-key-0001", "sha256:a", operation)

    assert executions == 1
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.response == first.response

    with pytest.raises(ProblemError) as error:
        store.execute(
            "idempotency-key-0001",
            "sha256:b",
            lambda: {"command_id": "must-not-run"},
        )
    assert error.value.problem.code == "IDEMPOTENCY_KEY_REUSED"
