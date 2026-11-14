# Contributing to FinGuard

## Local Development Setup

1. Start full stack: `make up`
2. Reset local test DB (`finguard_test`): `make test-db`
3. Run linters & type checks: `make lint`
4. Run backend & frontend tests: `make test`
5. Optional pre-commit hooks: `pip install pre-commit && pre-commit install`

## Pull Request Guidelines

- Keep `ruff`, `mypy`, `tsc`, `eslint`, `pytest`, and `vitest` passing before pushing.
- Never commit `.env` files, secrets, or local port overrides.
- Update `README.md` and `docs/` when adding or modifying endpoints or migrations.
