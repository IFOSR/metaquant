"""Append-only audit and at-least-once event delivery primitives."""

from collections.abc import Iterable
from threading import RLock
from typing import Protocol

from quant_platform.control_plane.contracts import AuditEvent, OutboxEnvelope


class AuditStore(Protocol):
    """Append-only persistence seam for PostgreSQL audit events."""

    def append(self, event: AuditEvent) -> None: ...

    def list(self) -> tuple[AuditEvent, ...]: ...


class OutboxStore(Protocol):
    """Transactional outbox persistence seam for PostgreSQL."""

    def append(self, envelope: OutboxEnvelope) -> None: ...

    def pending(self, limit: int = 100) -> tuple[OutboxEnvelope, ...]: ...

    def mark_published(self, event_id: str) -> None: ...


class ConsumerDeduplicator(Protocol):
    """Inbox/consumer deduplication seam for PostgreSQL."""

    def claim(self, event: OutboxEnvelope | str) -> bool: ...


class InMemoryAuditStore:
    """Small append-only reference implementation used by tests and local runs."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = RLock()

    def append(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    def list(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)


class InMemoryOutboxStore:
    """Reference outbox store; append and publish are replaced by one DB tx."""

    def __init__(self) -> None:
        self._pending: dict[str, OutboxEnvelope] = {}
        self._lock = RLock()

    def append(self, envelope: OutboxEnvelope) -> None:
        with self._lock:
            if envelope.event_id in self._pending:
                raise ValueError(f"event_id already exists: {envelope.event_id}")
            self._pending[envelope.event_id] = envelope

    def pending(self, limit: int = 100) -> tuple[OutboxEnvelope, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._lock:
            return tuple(list(self._pending.values())[:limit])

    def mark_published(self, event_id: str) -> None:
        with self._lock:
            self._pending.pop(event_id, None)


class InMemoryConsumerDeduplicator:
    """Deduplicates redelivered outbox events by immutable event ID."""

    def __init__(self) -> None:
        self._processed: set[str] = set()
        self._lock = RLock()

    def claim(self, event: OutboxEnvelope | str) -> bool:
        event_id = event if isinstance(event, str) else event.event_id
        if not event_id.strip():
            raise ValueError("event_id must not be blank")
        with self._lock:
            if event_id in self._processed:
                return False
            self._processed.add(event_id)
            return True

    def is_processed(self, event_id: str) -> bool:
        return event_id in self._processed

    def processed_ids(self) -> frozenset[str]:
        return frozenset(self._processed)


def deduplicate_events(
    events: Iterable[OutboxEnvelope],
    deduplicator: InMemoryConsumerDeduplicator,
) -> tuple[OutboxEnvelope, ...]:
    return tuple(event for event in events if deduplicator.claim(event))
