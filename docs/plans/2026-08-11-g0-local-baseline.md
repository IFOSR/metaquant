# G0 Local Runtime Baseline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a reproducible, minimal backend project and Docker Compose development stack.

**Architecture:** A FastAPI modular-monolith shell depends on Docker-managed PostgreSQL and MinIO. Alembic runs as a one-shot Compose dependency before the API, while Dagster and MLflow remain opt-in profiles.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, Alembic, MinIO, PostgreSQL 16, Docker Compose, uv, pytest, Ruff, mypy.

---

### Task 1: Define the health API contract

**Files:**
- Create: `tests/api/test_health.py`
- Create: `src/quant_platform/api/app.py`
- Create: `src/quant_platform/health.py`

**Steps:**
1. Write tests for live, ready, and degraded readiness responses.
2. Run the focused tests and verify they fail because the application package is absent.
3. Implement dependency-injected database and object-store probes.
4. Run the focused tests and verify all health contracts pass.

### Task 2: Add configuration and migration entry point

**Files:**
- Create: `src/quant_platform/config.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/20260811_0001_create_platform_health_probe.py`
- Create: `scripts/migrate.sh`

**Steps:**
1. Add configuration tests for environment loading and secret-safe defaults.
2. Implement settings and the Alembic environment.
3. Add the baseline migration with upgrade and downgrade paths.
4. Run unit tests and a migration against an empty Compose database.

### Task 3: Build the local Compose stack

**Files:**
- Create: `compose.yaml`
- Create: `Dockerfile`
- Create: `docker/postgres/init/00-create-app-user.sh`
- Create: `.dockerignore`
- Create: `.env.example`

**Steps:**
1. Define PostgreSQL and MinIO with pinned images, health checks, and named volumes.
2. Add one-shot bucket initialization and migration services.
3. Add the API and opt-in Dagster/MLflow profiles.
4. Validate with `docker compose config`.
5. Start the default stack and verify all health checks.

### Task 4: Add project tooling and documentation

**Files:**
- Create: `pyproject.toml`
- Create: `uv.lock`
- Create: `Makefile`
- Modify: `.gitignore`
- Modify: `README.md`

**Steps:**
1. Configure package metadata, dependencies, pytest, Ruff, and mypy.
2. Generate and validate the dependency lock.
3. Add Make targets for setup, startup, migration, checks, logs, and shutdown.
4. Document prerequisites, exact startup commands, optional profiles, data reset, and verification.
5. Run formatting, linting, type checking, tests, image build, migrations, and readiness checks.

