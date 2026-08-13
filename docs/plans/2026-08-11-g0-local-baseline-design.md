# G0 Local Runtime Baseline Design

## Scope

Build only the local engineering baseline required to start backend work. The
baseline includes a small FastAPI service, PostgreSQL and MinIO managed by
Docker Compose, Alembic migrations, health probes, optional Dagster and MLflow
profiles, and project-wide test and formatting configuration.

Factor IR, market models, research workflows, and all other business behavior
are explicitly out of scope.

## Architecture

The default Compose stack contains PostgreSQL, MinIO, a one-shot MinIO bucket
initializer, a one-shot Alembic migration container, and the API container.
PostgreSQL creates a non-superuser `quant_app` role and separate application
database during first initialization. Named volumes retain PostgreSQL, MinIO,
Dagster, and MLflow state.

Dagster and MLflow are functional but opt-in Compose profiles. This keeps the
normal G0 startup small while fixing the extension points and local ports for
later workers.

## Service Contract

The API exposes:

- `GET /health/live`: confirms that the API process is running.
- `GET /health/ready`: confirms PostgreSQL connectivity, the baseline
  migration table, MinIO connectivity, and the artifact bucket.

Readiness returns HTTP 503 and component-level status when a dependency is not
ready. It does not expose credentials or raw exception details.

## Tooling

Python 3.12 and `uv.lock` provide a reproducible environment. Ruff handles
formatting and linting, mypy provides static checking, and pytest provides
unit and API contract tests. Common commands are exposed through a Makefile
and documented in the repository README.

## Constraints

- PostgreSQL is never installed or initialized on the host.
- Secrets are loaded from `.env`, which remains ignored; `.env.example`
  contains development-only placeholders.
- The migration creates only a baseline health-probe table.
- Product and technical design documents under `doc/` are not modified.

