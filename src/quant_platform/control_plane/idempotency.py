"""Idempotency-Key validation and a deterministic in-memory reference store."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from quant_platform.control_plane.contracts import Problem, ProblemError


def validate_idempotency_key(value: str | None) -> str:
    if value is None or len(value.strip()) < 16:
        raise ProblemError(
            Problem(
                title="Idempotency-Key required",
                status=400,
                detail=(
                    "Every mutating command requires an Idempotency-Key "
                    "of at least 16 characters."
                ),
                code="INVALID_IDEMPOTENCY_KEY",
                request_id="unassigned",
                retryable=False,
            )
        )
    return value.strip()


@dataclass(frozen=True)
class IdempotencyRecord[T]:
    key: str
    request_fingerprint: str
    response: T
    stored_at: datetime


@dataclass(frozen=True)
class IdempotencyResult[T]:
    response: T
    replayed: bool


class IdempotencyStore[T](Protocol):
    """Persistence seam for a PostgreSQL-backed idempotency table."""

    def get(self, key: str) -> IdempotencyRecord[T] | None: ...

    def execute(
        self,
        key: str | None,
        request_fingerprint: str,
        operation: Callable[[], T],
    ) -> IdempotencyResult[T]: ...


class InMemoryIdempotencyStore[T]:
    """Reference semantics; production replaces storage with PostgreSQL."""

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord[T]] = {}
        self._lock = RLock()

    def get(self, key: str) -> IdempotencyRecord[T] | None:
        return self._records.get(validate_idempotency_key(key))

    def execute(
        self,
        key: str | None,
        request_fingerprint: str,
        operation: Callable[[], T],
    ) -> IdempotencyResult[T]:
        normalized_key = validate_idempotency_key(key)
        if not request_fingerprint.strip():
            raise ValueError("request_fingerprint must not be blank")
        with self._lock:
            existing = self._records.get(normalized_key)
            if existing is not None:
                if existing.request_fingerprint != request_fingerprint:
                    raise ProblemError(
                        Problem(
                            title="Idempotency key reused",
                            status=409,
                            detail=(
                                "The same Idempotency-Key was used for a "
                                "different command."
                            ),
                            code="IDEMPOTENCY_KEY_REUSED",
                            request_id="unassigned",
                            retryable=False,
                        )
                    )
                return IdempotencyResult(response=existing.response, replayed=True)
            response = operation()
            self._records[normalized_key] = IdempotencyRecord(
                key=normalized_key,
                request_fingerprint=request_fingerprint,
                response=response,
                stored_at=datetime.now(UTC),
            )
            return IdempotencyResult(response=response, replayed=False)
