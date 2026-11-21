# FinGuard Load Testing Results

## Test Configuration
- **Script**: `scripts/load_test_k6.js` (`grafana/k6` against local Docker Compose stack: FastAPI + PostgreSQL 16 + Redis 7)
- **Scenario**: 10 concurrent VUs for 20s executing authenticated `POST /transfers` (`amount_cents: 1`, unique `Idempotency-Key` per request) against a single hot source/destination account pair (`SELECT ... FOR UPDATE` serialized), followed by post-test balance-sum verification.

## Observed Results (2026-11-21)
- **Sustained throughput**: **25.37 transfers/sec** (514 completed transfers in 20.3s) on a single hot account pair
- **Transfer success rate**: **100.00%** (`514 / 514` `HTTP 201`)
- **Latency**: `avg = 383.48 ms`, `med = 385.36 ms`, `p90 = 428.65 ms`, `p95 = 440.91 ms`, `max = 520.23 ms`
- **Ledger drift**: **0 cents** (`src_balance + dst_balance = 1,000,000` cents exact)

## Scaling Bottleneck Note
All 10 VUs targeted a single account pair, so PostgreSQL row-level `FOR UPDATE` locking serialized writes to ~25 TPS. Across disjoint customer account pairs, throughput scales horizontally with DB connection pool and worker count.
