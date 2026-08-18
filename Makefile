.DEFAULT_GOAL := help

.PHONY: bootstrap build up down reset logs migrate test lint format typecheck check g3-integration optional help

bootstrap: ## Create a local environment file when one does not exist
	@test -f .env || cp .env.example .env

build: bootstrap ## Build the local application image
	docker compose build api

up: bootstrap ## Start PostgreSQL, MinIO, migrations, and API
	docker compose up --build -d

down: ## Stop local services without deleting data
	docker compose down

reset: ## Stop local services and delete named volumes
	docker compose down --volumes --remove-orphans

logs: ## Follow API, PostgreSQL, and MinIO logs
	docker compose logs --follow api postgres minio

migrate: bootstrap ## Apply all database migrations
	docker compose run --rm migrate

test: build ## Run unit and API tests in the application image
	docker compose run --rm --no-deps api pytest

lint: build ## Run Ruff lint checks
	docker compose run --rm --no-deps api ruff check .

format: build ## Format Python source and tests
	docker compose run --rm --no-deps api ruff format .

typecheck: build ## Run strict mypy checks
	docker compose run --rm --no-deps api mypy

check: build ## Run formatting, linting, type checking, and tests
	docker compose run --rm --no-deps api ruff format --check .
	docker compose run --rm --no-deps api ruff check .
	docker compose run --rm --no-deps api mypy
	docker compose run --rm --no-deps api pytest

g3-integration: build ## Verify G3 migrations, PostgreSQL concurrency, and MinIO hashes
	./scripts/verify-g3-infrastructure.sh

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z_-]+:.*## / {printf "%-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
