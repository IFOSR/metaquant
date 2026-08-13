#!/usr/bin/env bash
set -euo pipefail

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=app_user="$QUANT_DB_USER" \
  --set=app_password="$QUANT_DB_PASSWORD" \
  --set=app_db="$QUANT_DB_NAME" \
  --set=mlflow_db="$MLFLOW_DB_NAME" <<'EOSQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = :'app_user')
\gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'app_db', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'app_db')
\gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'mlflow_db', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'mlflow_db')
\gexec
EOSQL

psql \
  --username "$POSTGRES_USER" \
  --dbname "$QUANT_DB_NAME" \
  --set=app_user="$QUANT_DB_USER" <<'EOSQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT USAGE, CREATE ON SCHEMA public TO %I', :'app_user')
\gexec
EOSQL

