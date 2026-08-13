from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from quant_platform.control_plane.contracts import (
    AuditEvent,
    OutboxEnvelope,
    Problem,
    ProblemError,
)
from quant_platform.control_plane.idempotency import (
    IdempotencyRecord,
    IdempotencyResult,
    validate_idempotency_key,
)
from quant_platform.research.models import (
    AuditEventModel,
    ConsumerReceiptModel,
    IdempotencyRecordModel,
    OutboxEventModel,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqlAlchemyAuditStore:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def append(self, event: AuditEvent) -> None:
        try:
            with self._sessions.begin() as session:
                session.add(_audit_model(event))
        except IntegrityError as exc:
            raise ValueError(f"audit event already exists: {event.id}") from exc

    def list(self) -> tuple[AuditEvent, ...]:
        with self._sessions() as session:
            models = session.scalars(
                select(AuditEventModel).order_by(
                    AuditEventModel.occurred_at, AuditEventModel.id
                )
            ).all()
            return tuple(_audit_event(model) for model in models)


class SqlAlchemyOutboxStore:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def append(self, envelope: OutboxEnvelope) -> None:
        try:
            with self._sessions.begin() as session:
                session.add(_outbox_model(envelope))
        except IntegrityError as exc:
            raise ValueError(
                f"outbox event already exists: {envelope.event_id}"
            ) from exc

    def pending(self, limit: int = 100) -> tuple[OutboxEnvelope, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._sessions() as session:
            models = session.scalars(
                select(OutboxEventModel)
                .where(OutboxEventModel.published.is_(False))
                .order_by(OutboxEventModel.occurred_at, OutboxEventModel.event_id)
                .limit(limit)
            ).all()
            return tuple(_outbox_event(model) for model in models)

    def mark_published(self, event_id: str) -> None:
        with self._sessions.begin() as session:
            model = session.get(OutboxEventModel, event_id)
            if model is not None and not model.published:
                model.published = True
                model.published_at = _now()


class SqlAlchemyConsumerDeduplicator:
    def __init__(self, engine: Engine, *, consumer_id: str) -> None:
        if not consumer_id.strip():
            raise ValueError("consumer_id must not be blank")
        self._consumer_id = consumer_id
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def claim(self, event: OutboxEnvelope | str) -> bool:
        _event_id(event)
        raise RuntimeError(
            "claim does not represent processed; use execute(event, operation) "
            "so the consumer effect and receipt share one transaction"
        )

    def execute(
        self,
        event: OutboxEnvelope | str,
        operation: Callable[[Session], None],
    ) -> bool:
        """Run a database side effect and mark the event processed atomically."""
        event_id = _event_id(event)
        with self._sessions.begin() as session:
            try:
                session.add(
                    ConsumerReceiptModel(
                        consumer_id=self._consumer_id,
                        event_id=event_id,
                        processed_at=_now(),
                    )
                )
                session.flush()
            except IntegrityError:
                # Roll back the failed insert before leaving the transaction context.
                session.rollback()
                return False
            else:
                operation(session)
        return True


class SqlAlchemyIdempotencyStore[T]:
    def __init__(self, engine: Engine, *, namespace: str) -> None:
        if not namespace.strip():
            raise ValueError("namespace must not be blank")
        self._namespace = namespace
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def get(self, key: str) -> IdempotencyRecord[T] | None:
        normalized_key = validate_idempotency_key(key)
        with self._sessions() as session:
            model = session.get(
                IdempotencyRecordModel, (self._namespace, normalized_key)
            )
            if model is None:
                return None
            return IdempotencyRecord(
                key=model.idempotency_key,
                request_fingerprint=model.request_fingerprint,
                response=cast(T, model.response),
                stored_at=_utc(model.stored_at),
            )

    def execute(
        self,
        key: str | None,
        request_fingerprint: str,
        operation: Callable[[], T],
    ) -> IdempotencyResult[T]:
        normalized_key = validate_idempotency_key(key)
        if not request_fingerprint.strip():
            raise ValueError("request_fingerprint must not be blank")
        existing = self.get(normalized_key)
        if existing is not None:
            return self._replay(existing, request_fingerprint)

        response = operation()
        try:
            with self._sessions.begin() as session:
                session.add(
                    IdempotencyRecordModel(
                        namespace=self._namespace,
                        idempotency_key=normalized_key,
                        request_fingerprint=request_fingerprint,
                        response=cast(Any, response),
                        stored_at=_now(),
                    )
                )
        except IntegrityError:
            concurrent = self.get(normalized_key)
            if concurrent is None:
                raise
            return self._replay(concurrent, request_fingerprint)
        return IdempotencyResult(response=response, replayed=False)

    @staticmethod
    def _replay(
        existing: IdempotencyRecord[T], request_fingerprint: str
    ) -> IdempotencyResult[T]:
        if existing.request_fingerprint != request_fingerprint:
            raise ProblemError(
                Problem(
                    title="Idempotency key reused",
                    status=409,
                    detail=(
                        "The same Idempotency-Key was used for a different command."
                    ),
                    code="IDEMPOTENCY_KEY_REUSED",
                    request_id="unassigned",
                    retryable=False,
                )
            )
        return IdempotencyResult(response=existing.response, replayed=True)


def _audit_model(event: AuditEvent) -> AuditEventModel:
    return AuditEventModel(**event.model_dump())


def _audit_event(model: AuditEventModel) -> AuditEvent:
    return AuditEvent(
        id=model.id,
        occurred_at=_utc(model.occurred_at),
        actor=model.actor,
        action=model.action,
        resource_id=model.resource_id,
        resource_version=model.resource_version,
        reason=model.reason,
        parent_artifact_id=model.parent_artifact_id,
        request_id=model.request_id,
        correlation_id=model.correlation_id,
        policy_decision=model.policy_decision,
        before_hash=model.before_hash,
        after_hash=model.after_hash,
    )


def _event_id(event: OutboxEnvelope | str) -> str:
    event_id = event if isinstance(event, str) else event.event_id
    if not event_id.strip():
        raise ValueError("event_id must not be blank")
    return event_id


def _outbox_model(envelope: OutboxEnvelope) -> OutboxEventModel:
    return OutboxEventModel(
        **envelope.model_dump(),
        published=False,
        published_at=None,
    )


def _outbox_event(model: OutboxEventModel) -> OutboxEnvelope:
    return OutboxEnvelope(
        event_id=model.event_id,
        event_type=model.event_type,
        aggregate_type=model.aggregate_type,
        aggregate_id=model.aggregate_id,
        aggregate_version=model.aggregate_version,
        occurred_at=_utc(model.occurred_at),
        payload=model.payload,
        schema_version=model.schema_version,
        sequence=model.sequence,
    )
