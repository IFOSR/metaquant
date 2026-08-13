from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quant_platform.control_plane import (
    AuditEvent,
    FieldError,
    InMemoryAuditStore,
    OutboxEnvelope,
    Problem,
    ProblemError,
)

NOW = datetime(2026, 8, 11, tzinfo=UTC)


def test_problem_serializes_rfc_extensions_and_media_type() -> None:
    problem = Problem(
        type="https://quant.example/problems/validation",
        title="Invalid command",
        status=422,
        detail="One or more fields are invalid.",
        code="COMMAND_INVALID",
        request_id="req-42",
        retryable=False,
        current_version="17",
        field_errors=(
            FieldError(path="/reason", code="TOO_SHORT", message="Too short"),
        ),
    )

    assert problem.media_type == "application/problem+json"
    assert problem.model_dump(mode="json")["field_errors"][0]["path"] == "/reason"


def test_problem_rejects_non_error_status() -> None:
    with pytest.raises(ValidationError):
        Problem(
            title="Not an error",
            status=200,
            code="INVALID_STATUS",
            request_id="req-42",
            retryable=False,
        )


def test_audit_store_is_append_only_to_callers() -> None:
    event = AuditEvent(
        id="audit-1",
        occurred_at=NOW,
        actor="user-17",
        action="research.job.create",
        resource_id="job-1",
        resource_version="1",
        reason="Create the approved research task.",
        request_id="req-42",
        correlation_id="corr-42",
        policy_decision="ALLOW",
        after_hash="sha256:after",
    )
    store = InMemoryAuditStore()

    store.append(event)
    returned = store.list()

    assert returned == (event,)
    assert isinstance(returned, tuple)


def test_outbox_envelope_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        OutboxEnvelope.model_validate(
            {
                "event_id": "evt-1",
                "event_type": "ResearchJobCreated",
                "aggregate_type": "ResearchJob",
                "aggregate_id": "job-1",
                "aggregate_version": "1",
                "occurred_at": NOW,
                "payload": {},
                "untrusted_actor": "client-value",
            }
        )


def test_problem_error_exposes_serializable_problem() -> None:
    problem = Problem(
        title="Conflict",
        status=409,
        code="CONFLICT",
        request_id="req-42",
        retryable=True,
    )

    error = ProblemError(problem)

    assert error.problem is problem
    assert str(error) == "Conflict"
