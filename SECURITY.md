# Security Policy

## Supported Versions
Only the latest `main` branch of FinGuard is actively maintained with security patches.

## Reporting a Vulnerability
Please **do not** open a public GitHub issue for security vulnerabilities.
Report security issues privately via GitHub Security Advisories for `ayoubdk1/finguard`, including:
- Affected component or endpoint
- Reproduction steps or proof of concept
- Estimated impact

We aim to acknowledge reports within 48 hours and provide a remediation timeline within 5 business days.

## Security Controls
- Mandatory authentication, RBAC (`CUSTOMER`, `FRAUD_ANALYST`, `AUDITOR`, `ADMIN`), TOTP MFA with 64-bit Argon2id backup codes
- `httpOnly; SameSite=Strict` refresh cookies with `SELECT ... FOR UPDATE` reuse detection
- Append-only double-entry ledger and SHA-256 hash-chained `audit_log`
- Blocking CI security gates: `pip-audit`, `npm audit`, `Trivy`, `Gitleaks`, and `CodeQL`
