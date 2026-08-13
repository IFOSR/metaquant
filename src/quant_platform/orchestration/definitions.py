from dagster import Definitions, job, op


@op  # type: ignore[misc]  # Dagster decorators do not expose typed signatures.
def dispatch_experiment_run() -> str:
    """Dagster is a retryable worker seam, not the experiment state truth source."""
    return "control-plane-command-required"


@job  # type: ignore[misc]  # Keep the untyped boundary at the Dagster seam.
def experiment_execution_job() -> None:
    dispatch_experiment_run()


defs = Definitions(jobs=[experiment_execution_job])
