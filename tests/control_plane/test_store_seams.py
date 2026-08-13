from datetime import UTC, datetime

from quant_platform.control_plane import (
    InMemoryOutboxStore,
    OutboxEnvelope,
)

NOW = datetime(2026, 8, 11, tzinfo=UTC)


def test_in_memory_outbox_exposes_pending_and_publish_semantics() -> None:
    envelope = OutboxEnvelope(
        event_id="evt-1",
        event_type="ResearchJobCreated",
        aggregate_type="ResearchJob",
        aggregate_id="job-1",
        aggregate_version="1",
        occurred_at=NOW,
        payload={"state": "DRAFT"},
    )
    store = InMemoryOutboxStore()

    store.append(envelope)
    assert store.pending() == (envelope,)

    store.mark_published("evt-1")
    assert store.pending() == ()
