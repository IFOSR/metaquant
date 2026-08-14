from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.orchestration.dispatch import (
    dispatch_experiment_run,
)


def test_dispatch_returns_command_receipt() -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    def sender(method: str, path: str, body: dict[str, object]) -> dict[str, object]:
        calls.append((method, path, body))
        return {"command_id": "cmd_1", "resource_id": "run_1"}

    result = dispatch_experiment_run(
        "run_1",
        sender=sender,
        now=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
    )

    assert result.run_id == "run_1"
    assert result.command_id == "cmd_1"
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/v1/experiments/run_1:run"
    metadata = calls[0][2]["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["reason"] == "orchestrated"


def test_dispatch_rejects_missing_command_id() -> None:
    def sender(method: str, path: str, body: dict[str, object]) -> dict[str, object]:
        return {"error": "no command"}

    with pytest.raises(ValueError, match="command_id"):
        dispatch_experiment_run("run_1", sender=sender)


def test_dispatch_rejects_empty_run_id() -> None:
    with pytest.raises(ValueError, match="run_id"):
        dispatch_experiment_run("", sender=lambda m, p, b: {"command_id": "c"})
