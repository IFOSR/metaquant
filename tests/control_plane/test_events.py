from datetime import UTC, datetime

import pytest

from quant_platform.control_plane import (
    InMemoryConsumerDeduplicator,
    OutboxEnvelope,
    ProblemError,
    ReconnectState,
    deduplicate_events,
    reconnect_snapshot_required,
)

NOW = datetime(2026, 8, 11, tzinfo=UTC)


def event(event_id: str) -> OutboxEnvelope:
    return OutboxEnvelope(
        event_id=event_id,
        event_type="ResearchJobChanged",
        aggregate_type="ResearchJob",
        aggregate_id="job-1",
        aggregate_version="17",
        occurred_at=NOW,
        payload={"state": "RUNNING"},
        sequence=11891,
    )


def test_consumer_deduplicates_at_least_once_delivery() -> None:
    deduplicator = InMemoryConsumerDeduplicator()
    envelope = event("evt-1")

    assert deduplicator.claim(envelope) is True
    assert deduplicator.claim(envelope) is False
    assert deduplicator.is_processed("evt-1")


def test_batch_deduplication_preserves_first_delivery_order() -> None:
    deduplicator = InMemoryConsumerDeduplicator()

    accepted = deduplicate_events(
        [event("evt-1"), event("evt-1"), event("evt-2")],
        deduplicator,
    )

    assert tuple(item.event_id for item in accepted) == ("evt-1", "evt-2")


def test_reconnect_always_requires_authoritative_snapshot() -> None:
    instruction = reconnect_snapshot_required("job-1")

    assert instruction.must_refetch_snapshot is True
    assert instruction.reason == "RECONNECT"


def test_writes_remain_blocked_until_snapshot_is_refetched() -> None:
    state = ReconnectState(resource_id="job-1")

    with pytest.raises(ProblemError) as error:
        state.assert_writes_enabled("req-42")
    assert error.value.problem.code == "SNAPSHOT_REQUIRED"

    state.accept_snapshot("17")
    state.assert_writes_enabled("req-42")

    state.on_reconnect()
    with pytest.raises(ProblemError):
        state.assert_writes_enabled("req-43")
