"""Optional Dagster integration package.

The Dagster job is a retryable worker seam; the deterministic dispatch logic
lives in ``dispatch`` and is testable without the Dagster runtime.
"""

from quant_platform.orchestration.dispatch import (
    DispatchResult,
    dispatch_experiment_run,
    http_sender,
)

__all__ = [
    "DispatchResult",
    "dispatch_experiment_run",
    "http_sender",
]
