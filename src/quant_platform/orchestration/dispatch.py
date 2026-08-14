"""Orchestration dispatch logic (G16-011).

The Dagster job is a retryable worker seam, not the source of truth. Its op
delegates to this deterministic dispatcher, which issues control-plane
commands and reports the command receipt. Keeping the dispatch as a pure
function makes the orchestration testable without a Dagster runtime.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DispatchResult:
    run_id: str
    command_id: str
    submitted_at: str

    def payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "command_id": self.command_id,
            "submitted_at": self.submitted_at,
        }


CommandSender = Callable[[str, str, dict[str, object]], dict[str, object]]


def dispatch_experiment_run(
    run_id: str,
    *,
    sender: CommandSender,
    reason: str = "orchestrated",
    now: datetime | None = None,
) -> DispatchResult:
    """Dispatch an experiment run command to the control plane.

    ``sender`` is a (method, path, body) -> response callable that reaches the
    control-plane API. The orchestrator never mutates experiment state
    directly; it only issues the command and surfaces the receipt.
    """
    if not run_id or run_id.strip() != run_id:
        raise ValueError("run_id must be a non-empty normalized identifier")
    if not reason:
        raise ValueError("reason must not be empty")

    body: dict[str, object] = {
        "metadata": {"reason": reason, "parent_artifact_id": None}
    }
    response = sender("POST", f"/v1/experiments/{run_id}:run", body)
    command_id = response.get("command_id")
    if not isinstance(command_id, str) or not command_id:
        raise ValueError("control plane response missing command_id")
    submitted_at = now or datetime.now().astimezone()
    return DispatchResult(
        run_id=run_id,
        command_id=command_id,
        submitted_at=submitted_at.isoformat(),
    )


def http_sender(base_url: str) -> CommandSender:
    """Build a control-plane command sender backed by ``urllib``.

    Uses the standard library so the orchestration layer has no additional
    HTTP dependency. The base URL is injected by the worker environment.
    """
    import json as _json
    import urllib.request

    base = base_url.rstrip("/")

    def sender(method: str, path: str, body: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            base + path,
            data=_json.dumps(body).encode(),
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = _json.loads(response.read().decode())
        if not isinstance(payload, dict):
            raise ValueError("control plane response is not a JSON object")
        return payload

    return sender
