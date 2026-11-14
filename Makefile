.PHONY: up down test test-db test-backend test-frontend lint

PYTHON ?= python

up:
	docker compose up --build -d

down:
	docker compose down

test-db:
	$(PYTHON) backend/scripts/reset_test_db.py

test-backend:
	cd backend && PYTHONPATH=. pytest -v

test-frontend:
	cd frontend && npm test

test: test-backend test-frontend

lint:
	cd backend && ruff check app && mypy app --config-file pyproject.toml
	cd frontend && npm run lint && npx tsc -b --noEmit
