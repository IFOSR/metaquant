import pytest

from quant_platform.control_plane import (
    InMemoryIdempotencyStore,
    ProblemError,
    validate_idempotency_key,
)


def test_idempotency_replay_does_not_execute_command_twice() -> None:
    executions = 0
    store: InMemoryIdempotencyStore[dict[str, str]] = InMemoryIdempotencyStore()

    def execute() -> dict[str, str]:
        nonlocal executions
        executions += 1
        return {"command_id": "cmd-1"}

    first = store.execute("idempotency-key-0001", "sha256:request-a", execute)
    replay = store.execute("idempotency-key-0001", "sha256:request-a", execute)

    assert executions == 1
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.response == first.response


def test_idempotency_key_cannot_be_reused_for_different_command() -> None:
    store: InMemoryIdempotencyStore[str] = InMemoryIdempotencyStore()
    store.execute("idempotency-key-0001", "sha256:request-a", lambda: "accepted")

    with pytest.raises(ProblemError) as error:
        store.execute(
            "idempotency-key-0001",
            "sha256:request-b",
            lambda: "must-not-run",
        )

    assert error.value.problem.code == "IDEMPOTENCY_KEY_REUSED"
    assert error.value.problem.status == 409


@pytest.mark.parametrize("key", [None, "", "short"])
def test_mutation_requires_valid_idempotency_key(key: str | None) -> None:
    with pytest.raises(ProblemError) as error:
        validate_idempotency_key(key)

    assert error.value.problem.code == "INVALID_IDEMPOTENCY_KEY"
