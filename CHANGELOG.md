# Changelog

All notable changes to FinGuard are documented in this file.

## [Unreleased]
### Added
- `.github/CODEOWNERS`, PR template with rollback checklist, `SECURITY.md`, and `docs/stride-threat-model.md`.
- Real-concurrency `committed_world` pytest fixture and Hypothesis property-based ledger invariant tests.

## [0.15.0] - 2026-11-27
### Added
- SHA-256 hash chain (`prev_hash`, `hash`, `actor_role`, `before`, `after`) on `audit_log` plus `backend/scripts/verify_audit_chain.py`.
- PostgreSQL immutability trigger blocking updates to `transactions.status` and `transactions.description`.
- Cursor-paginated `GET /audit` endpoint restricted to `AUDITOR` role and full route audit instrumentation.

## [0.14.0] - 2026-11-26
### Added
- Migration `0019` with `CREATE INDEX CONCURRENTLY` scalability indexes and `account_balances` projection table.
- Lock-free `SYSTEM_*` account handling in `post_transaction` and keyset cursor pagination across `/accounts/{id}/transactions`, `/fraud/alerts`, and `/admin/users`.
- Nginx `X-Forwarded-For` overwrite (`$remote_addr`), unpublished backend port `8001`, `(email, IP)` progressive login delay, and 0?100 risk score normalization.

## [0.13.0] - 2026-11-25
### Security
- Remediated audit findings #1?#18: distributed password-spray protection, atomic FX refund locking with deadlock retry, fail-closed pre-settlement fraud scoring, ledger indexes, MFA UI + password-gated enrollment, refresh-token rotation row locking, constant-time login check, admin password policy & four-eyes governance, SMTP `STARTTLS`, `Cache-Control: no-store`, and authenticated `/metrics` & `/health/ready`.
