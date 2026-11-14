.PHONY: test-db test-backend test-frontend lint

PYTHON ?= python

test-db:
	$(PYTHON) backend/scripts/reset_test_db.py

test-backend:
	cd backend && PYTHONPATH=. pytest -v

test-frontend:
	cd frontend && npm test

lint:
	cd backend && ruff check app && mypy app --config-file pyproject.toml
	cd frontend && npm run lint && npx tsc -b --noEmit
