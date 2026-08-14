"""Dagster job definitions (G16-011).

The Dagster job is a retryable worker seam, not the experiment state truth
source. Each op delegates to the deterministic dispatcher, which issues a
control-plane command; the worker never mutates experiment state directly.
"""

from __future__ import annotations

import os

from dagster import Definitions, job, op

from quant_platform.orchestration.dispatch import dispatch_experiment_run, http_sender

_CONTROL_PLANE_URL = os.environ.get("QUANT_CONTROL_PLANE_URL", "http://localhost:8000")


@op  # type: ignore[misc]  # Dagster decorators do not expose typed signatures.
def dispatch_experiment_run_command(run_id: str) -> dict[str, object]:
    """Dispatch an experiment run command to the control plane."""
    return dispatch_experiment_run(
        run_id, sender=http_sender(_CONTROL_PLANE_URL)
    ).payload()


@job  # type: ignore[misc]  # Keep the untyped boundary at the Dagster seam.
def experiment_execution_job() -> None:
    dispatch_experiment_run_command()


defs = Definitions(jobs=[experiment_execution_job])
