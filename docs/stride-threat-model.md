# FinGuard STRIDE Threat Model

## Scope & Trust Boundaries
1. **Browser -> Nginx Reverse Proxy** (public boundary; TLS termination, `X-Forwarded-For` overwrite).
2. **Nginx -> FastAPI Backend** (internal Docker network; backend port unpublished).
3. **FastAPI -> PostgreSQL / Redis / Redpanda** (data & messaging tier; password-protected Redis, immutable ledger & audit triggers).

## Threat Analysis

| Category | Threat Example | Mitigation Implemented | Residual / Planned |
| --- | --- | --- | --- |
| **Spoofing** | Credential stuffing, MFA bypass, forged `X-Forwarded-For` | Argon2id + constant-time dummy verify, `(email, IP)` progressive delay, TOTP + 64-bit Argon2id backup codes, Nginx `$remote_addr` overwrite | WebAuthn/passkeys, step-up tokens bound to transfer payload (Stage B 2.7) |
| **Tampering** | Modifying posted ledger entries, transactions, or audit logs | Append-only DB triggers on `ledger_entries`, `audit_log`, and `transactions` (`status`/`description`), SHA-256 audit hash chain | Least-privilege `finguard_app` DB role without `UPDATE`/`DELETE` grants (Stage B 3.2) |
| **Repudiation** | Disputed admin actions, deposits, or fraud overrides | Transactional `audit_log` with `actor_id`, `actor_role`, `before`/`after` JSONB, `request_id`, and nightly chain verifier | Four-eyes maker-checker on manual deposits & limit changes (Stage B 2.5) |
| **Information Disclosure** | Timing-based user enumeration, cached sensitive responses, unauthenticated `/metrics` | Constant-time login check, `Cache-Control: no-store`, authenticated `/metrics` & `/health/ready`, SMTP `STARTTLS`, PII masking in logs | Column-level PII encryption & TLS `verify-full` to Postgres/Redis/Kafka (Stage B/C) |
| **Denial of Service** | Account lockout DoS, unpaginated history queries, hot-row lock contention | Failure-only rate limiting, keyset cursor pagination + `CONCURRENTLY` indexes, lock-free `SYSTEM_*` accounts | PgBouncer & monthly `ledger_entries` partitioning (Stage C) |
| **Elevation of Privilege** | Direct self-promotion to `ADMIN`, stolen session enrolling attacker MFA | Four-eyes approval required for `ADMIN` promotion, password + fresh `auth_time` required on `/auth/mfa/setup` | Dedicated `SUPPORT` and `COMPLIANCE_OFFICER` roles (Stage C) |
