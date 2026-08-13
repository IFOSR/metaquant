"""Control-plane consistency, audit, and event contracts."""

from quant_platform.control_plane.concurrency import (
    ETag,
    format_etag,
    matches_if_match,
    parse_strong_etag,
    require_if_match,
)
from quant_platform.control_plane.contracts import (
    AuditEvent,
    FieldError,
    OutboxEnvelope,
    Problem,
    ProblemError,
    ReconnectState,
    SnapshotRequired,
    reconnect_snapshot_required,
    utc_now,
)
from quant_platform.control_plane.events import (
    AuditStore,
    ConsumerDeduplicator,
    InMemoryAuditStore,
    InMemoryConsumerDeduplicator,
    InMemoryOutboxStore,
    OutboxStore,
    deduplicate_events,
)
from quant_platform.control_plane.idempotency import (
    IdempotencyRecord,
    IdempotencyResult,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    validate_idempotency_key,
)
from quant_platform.control_plane.persistence import (
    SqlAlchemyAuditStore,
    SqlAlchemyConsumerDeduplicator,
    SqlAlchemyIdempotencyStore,
    SqlAlchemyOutboxStore,
)

__all__ = [
    "AuditEvent",
    "AuditStore",
    "ConsumerDeduplicator",
    "ETag",
    "FieldError",
    "IdempotencyRecord",
    "IdempotencyResult",
    "InMemoryAuditStore",
    "InMemoryConsumerDeduplicator",
    "InMemoryIdempotencyStore",
    "InMemoryOutboxStore",
    "IdempotencyStore",
    "OutboxEnvelope",
    "OutboxStore",
    "Problem",
    "ProblemError",
    "ReconnectState",
    "SnapshotRequired",
    "SqlAlchemyAuditStore",
    "SqlAlchemyConsumerDeduplicator",
    "SqlAlchemyIdempotencyStore",
    "SqlAlchemyOutboxStore",
    "deduplicate_events",
    "format_etag",
    "matches_if_match",
    "parse_strong_etag",
    "reconnect_snapshot_required",
    "require_if_match",
    "utc_now",
    "validate_idempotency_key",
]
