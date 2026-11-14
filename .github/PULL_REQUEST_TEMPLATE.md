## Summary
- Briefly describe what changed and why.

## Verification Checklist
- [ ] `ruff check app` & `mypy app --config-file pyproject.toml` pass
- [ ] `pytest` passes locally
- [ ] `tsc -b --noEmit`, `eslint .`, and `vitest run` pass
- [ ] Alembic migrations tested (`upgrade head` -> `downgrade base` -> `upgrade head`)
