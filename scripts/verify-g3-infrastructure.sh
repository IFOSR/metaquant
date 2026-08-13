#!/usr/bin/env sh
set -eu

database="g3_gate_$(date +%Y%m%d_%H%M%S)_$$"
database_url="postgresql+psycopg://quant_app:quant_app_dev@postgres:5432/$database"
export POSTGRES_PORT="${POSTGRES_PORT:-55432}"

cleanup() {
  docker compose exec -T postgres psql \
    -U "${POSTGRES_SUPERUSER:-postgres}" \
    -d "${POSTGRES_BOOTSTRAP_DB:-postgres}" \
    -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$database' AND pid <> pg_backend_pid()" \
    -c "DROP DATABASE IF EXISTS $database"
}

trap cleanup EXIT INT TERM

docker compose up -d postgres minio
docker compose up minio-init
docker compose exec -T postgres psql \
  -U "${POSTGRES_SUPERUSER:-postgres}" \
  -d "${POSTGRES_BOOTSTRAP_DB:-postgres}" \
  -v ON_ERROR_STOP=1 \
  -c "CREATE DATABASE $database OWNER ${QUANT_DB_USER:-quant_app}"

docker compose run --rm --no-deps \
  -e DATABASE_URL="$database_url" \
  -v "$PWD/alembic:/app/alembic" \
  -v "$PWD/src:/app/src" \
  migrate alembic upgrade head
docker compose run --rm --no-deps \
  -e DATABASE_URL="$database_url" \
  -v "$PWD/alembic:/app/alembic" \
  -v "$PWD/src:/app/src" \
  migrate alembic downgrade 20260812_0004
docker compose run --rm --no-deps \
  -e DATABASE_URL="$database_url" \
  -v "$PWD/alembic:/app/alembic" \
  -v "$PWD/src:/app/src" \
  migrate alembic upgrade head
docker compose run --rm --no-deps \
  -e G3_TEST_DATABASE_URL="$database_url" \
  -e G3_TEST_MINIO_ENDPOINT="minio:9000" \
  -v "$PWD/src:/app/src" \
  -v "$PWD/tests:/app/tests" \
  api pytest tests/integration/test_g3_infrastructure.py -q
