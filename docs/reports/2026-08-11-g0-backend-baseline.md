# G0 Backend Baseline Delivery Report

## Delivered

- Python 3.12 package using FastAPI, Pydantic v2, SQLAlchemy, Alembic, and
  MinIO.
- Docker Compose default stack for PostgreSQL 16, MinIO, bucket
  initialization, one-shot migrations, and API startup.
- PostgreSQL first-run bootstrap with a non-superuser `quant_app` role,
  `quant_platform` application database, and separate `quant_mlflow`
  database.
- Named volumes for PostgreSQL, MinIO, and the optional Dagster runtime.
- Functional optional Compose profiles for Dagster and MLflow.
- `/health/live` and dependency-aware `/health/ready` endpoints.
- Initial reversible Alembic migration for `platform_health_probe`.
- Reproducible `uv.lock`, Ruff, strict mypy, pytest, Dockerfile, Makefile,
  `.env.example`, and local startup documentation.

No Factor IR, market model, research workflow, or other quant business logic
was implemented.

## Validation Evidence

Static and test baseline:

```text
$ make check
11 files already formatted
All checks passed!
Success: no issues found in 9 source files
collected 4 items
4 passed
```

Compose and migration:

```text
$ docker compose config
exit 0

$ docker compose run --rm migrate alembic current
20260811_0001 (head)

$ docker compose run --rm migrate alembic upgrade head
exit 0 on an already-migrated database
```

The shared host already used the default PostgreSQL port, so the runtime
smoke test used temporary host-port overrides without changing container
ports:

```bash
POSTGRES_PORT=15432 \
MINIO_API_PORT=19000 \
MINIO_CONSOLE_PORT=19001 \
API_PORT=18000 \
docker compose up -d
```

Runtime results:

```text
postgres: healthy
minio: healthy
api: healthy

$ curl http://localhost:18000/health/live
{"service":"quant-platform-api","status":"ok"}

$ curl http://localhost:18000/health/ready
{"status":"ok","checks":{"postgres":"ok","minio":"ok"}}
```

Database and object-store checks:

```text
quant_app|rolsuper=false|rolcreatedb=false|rolcreaterole=false
platform_health_probe owner: quant_app
MinIO buckets: artifacts, mlflow
```

Both optional profiles pass Compose schema/config validation:

```bash
docker compose --profile orchestration --profile tracking config --quiet
```

## Startup Commands

```bash
make bootstrap
make up
docker compose ps
curl --fail http://localhost:8000/health/live
curl --fail http://localhost:8000/health/ready
make check
```

If a default host port is occupied, change the corresponding value in the
ignored `.env` file using `.env.example` as the template.

## Known Constraints

- Default port `5432` was occupied in the shared validation environment.
  Alternate host ports verified the stack end to end.
- Dagster and MLflow are opt-in extension points. Their Compose definitions
  and dependency lock resolve successfully, but this G0 task did not run their
  full UI/runtime smoke tests.
- Docker Desktop or another active Docker Engine is required; PostgreSQL is
  intentionally not supported as a host installation.

