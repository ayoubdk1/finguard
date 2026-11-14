# FinGuard — Real-Time Fintech Ledger, FX & AI Fraud Detection Platform

[[https://github.com/ayoubdk1/finguard/actions/workflows/ci.yml/badge.svg?branch=main]](https://github.com/ayoubdk1/finguard/actions/workflows/ci.yml)

FinGuard is a full-stack financial engineering and fraud detection platform built with **FastAPI**, **SQLAlchemy 2.0**, **PostgreSQL 16**, **Redis 7**, **Redpanda (Kafka)**, **scikit-learn**, and **React 19 + TypeScript + Vite**.

## Key Capabilities

- **Double-Entry Ledger & Idempotent Transfers**: ACID-compliant balance updates with pessimistic row-level locking (SELECT ... FOR UPDATE), idempotency keys, and full audit trails.
- **Multi-Currency & FX Engine**: Exact Decimal currency conversion across USD, EUR, and TND with automated SYSTEM_FX clearing accounts.
- **Transaction Security & Velocity Controls**: Configurable per-transaction ($10,000) and rolling 24-hour ($50,000) transfer limits, plus atomic full-transfer refunds (POST /transfers/{id}/refund).
- **AI Fraud Scoring & Analyst Workflow**: Real-time transaction risk scoring, automated FraudAlert generation, and investigation/resolution workflows (/fraud/alerts, /investigate, /resolve).
- **Enterprise Auth, RBAC, Sessions & MFA**: Granular RBAC (CUSTOMER, ADMIN, FRAUD_ANALYST, AUDITOR), JWT + rotating refresh tokens with reuse detection, session management (/auth/sessions), and TOTP MFA (/auth/mfa/*).
- **Distributed Reliability & Resilience**: Redis-backed sliding-window rate limiting with graceful fallback, CircuitBreaker, and exponential backoff with jitter.
- **Production Engineering**: Multi-stage Dockerfiles (ackend/Dockerfile, rontend/Dockerfile + Nginx reverse proxy), structured JSON logging (JsonFormatter), and /health + /health/ready readiness probes.

## Resetting the Test DB

Run `make test-db` or `python backend/scripts/reset_test_db.py` to recreate `finguard_test`.
