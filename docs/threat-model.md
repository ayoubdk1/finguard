# FinGuard Threat Model & Token Storage Tradeoff

## 1. Token Handling & Storage Tradeoff
- **Current implementation**: `frontend/src/services/api.ts` stores the short-lived JWT access token (`15m` TTL) and rotating refresh token in `localStorage` so the SPA survives page reloads without a dedicated BFF/cookie-refresh endpoint.
- **Residual XSS risk**: Any successful XSS payload in the origin could read tokens from `localStorage`.
- **Target architecture (recommended)**: Keep the access token strictly in JavaScript memory (React state/closure) and store the refresh token in an `httpOnly; Secure; SameSite=Strict` cookie scoped to `/auth/refresh` and `/auth/logout`, paired with CSRF origin/header checks.
- **Why documented now**: Moving to `httpOnly` cookies requires cross-origin `credentials: 'include'` CORS tightening and updating all backend/frontend auth test suites.

## 2. Existing Mitigations
- **Short access-token TTL & refresh rotation**: Refresh tokens are single-use (`rotate_refresh_token`); token reuse revokes the entire session family (`family_id`).
- **Step-up authentication**: Sensitive actions (`/auth/mfa/*`) enforce `require_recent_login`.
- **Content Security Policy & headers**: Production CSP restricts script sources (`script-src 'self'`), reducing XSS surface.
- **Session & password controls**: Users can inspect and revoke active sessions (`/auth/sessions`) and rotate passwords (`/auth/change-password`, revoking all active sessions).
