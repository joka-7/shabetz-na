# Development tasks. Run `make help` for a summary.
.DEFAULT_GOAL := help
SHELL := /bin/bash

UV ?= uv run --extra dev
NPM ?= npm --prefix frontend

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install backend and frontend dependencies
	uv sync --extra dev
	$(NPM) install

.PHONY: db-up
db-up: ## Start MySQL in the background
	docker compose up -d db

.PHONY: db-down
db-down: ## Stop MySQL
	docker compose down

.PHONY: migrate
migrate: ## Apply database migrations
	$(UV) alembic upgrade head

.PHONY: seed
seed: ## Populate an example configuration
	$(UV) shabetz seed-demo

.PHONY: api
api: ## Run the API with reload
	$(UV) uvicorn shabetz.api.main:app --reload --port 8000

.PHONY: ui
ui: ## Run the frontend dev server
	$(NPM) run dev

.PHONY: dev
dev: ## Run API and frontend together
	@trap 'kill 0' EXIT; \
	$(UV) uvicorn shabetz.api.main:app --reload --port 8000 & \
	$(NPM) run dev & \
	wait

.PHONY: test
test: ## Run all tests
	$(UV) pytest
	$(NPM) run test

.PHONY: lint
lint: ## Lint and typecheck
	$(UV) ruff check src tests
	$(UV) ruff format --check src tests
	$(UV) mypy
	$(NPM) run lint

.PHONY: fmt
fmt: ## Format Python sources
	$(UV) ruff format src tests
	$(UV) ruff check --fix src tests

.PHONY: types
types: ## Regenerate frontend API types from the running API
	@echo "Requires the API on :8000 (make api)"
	npx --yes openapi-typescript http://127.0.0.1:8000/openapi.json -o frontend/src/types/api.ts

.PHONY: check
check: lint test ## Lint, typecheck and test everything
