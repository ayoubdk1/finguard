# Compliance, Audit & Data Protection Policy

## 1. Append-Only Audit Log
- `audit_log` records actor, action, resource, masked IP address, `request_id`, and timestamp for login success/failure, MFA changes, role/status changes, admin password resets, refunds, fraud decisions, and deposit approvals.
- PostgreSQL trigger `trg_audit_log_immutable` blocks `UPDATE` and `DELETE` on `audit_log`.

## 2. Idempotency Key Retention
- Every `Transaction` sets `idempotency_expires_at` to `24 hours` after creation.
- `cleanup_expired_idempotency_keys()` expires keys past `idempotency_expires_at` so keys can be safely rotated without deleting ledger history.

## 3. PII Classification & Log Masking
- **PII Fields**: `users.email`, `users.full_name`, `login_history.ip_address`, `audit_log.ip_address` (stored masked), `users.mfa_secret` (Fernet encrypted at rest).
- **Masking**: `mask_email()`, `mask_ip()`, and `mask_pii_in_text()` redact email local parts and last IP octets before writing logs or audit details.
- **Retention**: Ledger and audit records are retained for 7 years; expired refresh tokens and idempotency scopes are purged/expired on schedule.

## 4. Ledger Reconciliation Alerting
- `backend/scripts/reconcile_ledger.py` updates `finguard_ledger_reconciliation_imbalance` (`0` = reconciled, `1` = imbalance) and `finguard_ledger_reconciliation_last_run_timestamp_seconds`.
- Prometheus alert `LedgerReconciliationImbalance` in `monitoring/prometheus/alerts.yml` fires when `finguard_ledger_reconciliation_imbalance != 0`.
