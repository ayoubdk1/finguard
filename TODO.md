# FinGuard Engineering TODO

## Phase 0 - Safety Net
- [x] Tag `v0.9-baseline` on `origin/main`
- [x] Add `.gitattributes` (`* text=auto eol=lf`)
- [x] Create `feat/ui-redesign` branch from `origin/main`
- [x] Remove `try_constraints.py`, `try_service.py`, `check_db.py`, `infra/`, `_legacy_register_unused`
- [x] Create `TODO.md`

## Phase 1 - Security & Auth (P0)
- [x] Isolate `mfa_pending` token (`aud=finguard-mfa`) and enforce `type == access`
- [x] Enforce `Permission.USER_MANAGE` on `POST /users`
- [x] Hide `reset_token` in `/auth/forgot-password` unless `FINGUARD_EXPOSE_RESET_TOKEN=1`
- [x] Encrypt `User.mfa_secret` at rest and add security headers (`CSP`, `HSTS`)

## Phase 2 - Financial Correctness (P1)
- [x] Currency-aware limits (`CURRENCY_EXPONENTS`) and sorted UUID locking
- [x] Atomic multi-leg FX transfers & duplicate-refund protection (`original_transaction_id`)
- [x] Scoped idempotency `(user_id, endpoint, key)` + `request_hash`
- [x] CI ledger reconciliation (`backend/scripts/reconcile_ledger.py`)

## Phase 3 - Real Fraud Detection (P2)
- [x] Server-side feature computation & auto `FraudAlert` creation on `POST /transfers`
- [x] Rules-only fallback when `.joblib` is unavailable + model `.meta.json` sidecar
- [x] Alert state machine (`PENDING -> INVESTIGATING -> APPROVED/BLOCKED`) & owner suspension on `BLOCKED`

## Phase 4 - Reliability, Observability & CI (P3)
- [x] Modular routers (`auth`, `accounts`, `transfers`, `fraud`, `admin`) & `X-Request-ID` middleware
- [x] Sliding-window Redis `ZSET` rate limiter with `CircuitBreaker` & jittered backoff
- [x] `prometheus_client` metrics, Grafana dashboard JSON, & `outbox-publisher` `DEAD` state worker
- [x] Full CI (`ruff`, `mypy`, Alembic round-trip, `pytest --cov`, `tsc`, `eslint`, `vitest`, `gitleaks`, `trivy`)

## Phase 5 - UI Redesign & Production Deployment
- [ ] Port UI redesign onto `feat/ui-redesign` and open PR
- [ ] Add UI & Grafana screenshots in `docs/screenshots/`
- [ ] Cloud production deployment & live bank rail integrations

