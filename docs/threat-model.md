# FinGuard Threat Model & Token Storage Architecture

## 1. Token Handling & Storage Architecture
- **Access tokens (in-memory only)**: `frontend/src/services/api.ts` holds the short-lived JWT access token (`15m` TTL) strictly in JavaScript memory (`inMemoryAccessToken`), preventing `localStorage` exfiltration via XSS.
- **Refresh tokens (`httpOnly; SameSite=Strict` cookie)**: `/auth/login`, `/auth/mfa/login`, and `/auth/refresh` issue `finguard_refresh_token` as an `httpOnly; SameSite=Strict` cookie (`Secure` in production), cleared on `/auth/logout`.
- **Silent session bootstrap**: On page reload, the SPA calls `/auth/me` -> on `401`, `fetchWithAuth` refreshes the in-memory access token via `POST /auth/refresh` with `credentials: 'include'`.

## 2. Mitigations
- **Refresh token rotation & reuse detection**: Refresh tokens are single-use (`rotate_refresh_token`); reuse revokes the entire session family (`family_id`).
- **Immediate access-token revocation**: `/auth/logout` revokes the access token `jti` in Redis (`is_access_token_revoked`).
- **Step-up authentication & CSP**: Sensitive MFA actions require recent login, and production CSP restricts script sources (`script-src 'self'`).
