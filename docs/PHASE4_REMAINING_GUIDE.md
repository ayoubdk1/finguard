# FinGuard — Complete remaining Phase 4 pack

> Simulation only. Compatible with the existing FastAPI/PostgreSQL ledger, Alembic
> revision `44b47c86ac8d`, `OutboxEvent`, `enqueue_transfer_posted`,
> Redpanda broker exposed at `localhost:19092`, and topic
> `finguard.transfers.posted.v1`.
>
> **Never overwrite your existing `main.py`, `ledger.py`, `models.py`, or `docker-compose.yml` with files from this pack.** All packaged Python files are new, except for the explicit class snippet to append to `models.py`.

## Task 4.3 — Finish broker test

From `C:\Users\user\finguard` in PowerShell:

```powershell
'45' | Out-Null  # optional no-op
'{"event_type":"TransferPosted","transaction_id":"manual-smoke-test","amount_cents":2000,"currency":"TND"}' | docker exec -i finguard-redpanda rpk topic produce finguard.transfers.posted.v1
docker exec finguard-redpanda rpk topic consume finguard.transfers.posted.v1 -n 1 -o start -f '%v\n'
```

**Note:** The manually produced event is deliberately *not* the full v1 event envelope and will later be redirected to the DLQ by the consumer. That is fine for this connectivity smoke test.

## Task 4.4 — Add publisher + consumer and migrations

1. Copy all provided `backend/...` new files into the same locations in your existing project.
2. Add the `ProcessedEvent` class from `docs/processed-event-model-addition.txt` to the **bottom** of your existing `backend/app/db/models.py`. Do not copy the comment lines and do not replace any existing model.
3. Open terminal in `C:\Users\user\finguard\backend`.

```powershell
cd C:\Users\user\finguard\backend
.\.venv\Scripts\python.exe -m pip install -r .\requirements-streaming.txt
.\.venv\Scripts\python.exe -m py_compile .\app\services\event_streaming.py .\scripts\publish_outbox.py .\scripts\consume_transfers.py .\app\db\models.py
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

Expected Alembic head: `0004`. This adds `processed_events` to the development database, without modifying `outbox_events` or ledger tables.

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://finguard:finguard@localhost:5432/finguard_test'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:DATABASE_URL
```

The suite should contain the previous 46 tests **plus 2 new tests**, assuming all earlier tests are present. Do not treat a count alone as proof; there must be zero failed tests.

### Redpanda DLQ topic

From root:

```powershell
cd C:\Users\user\finguard
docker exec finguard-redpanda rpk topic create finguard.transfers.posted.dlq.v1 -p 1 -r 1 --if-not-exists
docker exec finguard-redpanda rpk topic list
```

### Task 4.5 — Make a real simulated transfer

Start FastAPI from `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

In Swagger `http://127.0.0.1:8000/docs`, confirm source account balance is sufficient, then call `POST /transfers` using a **new** `Idempotency-Key`.

Illustrative development accounts previously created in FinGuard (confirm these still exist before using):

```json
{
  "source_account_id": "007c9f83-03db-48fd-bdae-9024fea8f52a",
  "destination_account_id": "b72238cf-a238-4fac-81a1-6421f192f7c7",
  "amount_cents": 100,
  "description": "Phase 4 streaming demo"
}
```

`100` is in the project's current simulated **integer cents** convention. Do not reuse an idempotency key from an earlier transfer.

Verify the new outbox record (root terminal):

```powershell
docker exec finguard-db psql -U finguard -d finguard -c "SELECT event_type, published_at, publish_attempts FROM outbox_events ORDER BY created_at DESC LIMIT 5;"
```

### Task 4.6 — Run publisher

From `backend`:

```powershell
cd C:\Users\user\finguard\backend
.\.venv\Scripts\python.exe -m scripts.publish_outbox --once
```

You should see one or more delivered events if pending transfer outbox rows exist. Verify `published_at` is no longer NULL. To run continuously in its own terminal:

```powershell
.\.venv\Scripts\python.exe -m scripts.publish_outbox --loop
```

### Task 4.7 — Run consumer

Open a **new** backend terminal, leave the publisher running in its own terminal:

```powershell
.\.venv\Scripts\python.exe -m scripts.consume_transfers
```

This starts at the earliest topic offset for its new group. The initial manual smoke-test event may appear as `Invalid event -> DLQ`. Complete envelopes emitted by the outbox publisher should appear as `Processed: <uuid>`.

Database check:

```powershell
docker exec finguard-db psql -U finguard -d finguard -c "SELECT event_type, count(*) FROM processed_events GROUP BY event_type;"
```

Stop long-running publisher/consumer via `Ctrl+C`.

### Task 4.8 — Reliability and final tests

`tests/test_event_streaming.py` verifies:
- Broker failure leaves the event unpublished and increments attempts.
- A later retry marks it published.
- A second consumer processing attempt does not insert a duplicate event ID.

Additionally, `tests/test_transfer_outbox.py` from your existing project verifies ledger-outbox atomicity and transfer idempotency. No real Redpanda broker is needed for pytest; it uses a fake producer.

Manual optional broker outage check: stop Redpanda, issue a simulated transfer, run `--once`, observe `published_at` NULL; restart Redpanda and rerun `--once`, observe non-NULL timestamp. The producer may block for its delivery timeout while Redpanda is down. Never use `docker compose down -v`.

### Task 4.9 — Git checkpoint

From project root, after all tests pass:

```powershell
cd C:\Users\user\finguard
git status --short
git diff --check
```

In VS Code **Source Control**, stage the relevant new files, `backend/app/db/models.py`, and (if not already committed) `docker-compose.yml`. Do not stage credentials, `.venv`, or transient output. Commit message:

`feat(streaming): publish and consume outbox events via Redpanda`

Verify:

```powershell
git log -1 --oneline
git status --short
```

## Architecture and caveats

```
POST /transfers
   -> PostgreSQL transaction: ledger entries + outbox_events row (atomic)
   -> separate publisher reads pending outbox row using FOR UPDATE SKIP LOCKED
   -> Kafka delivery acknowledged -> mark published_at
   -> Redpanda topic finguard.transfers.posted.v1
   -> consumer validates the v1 envelope
   -> PostgreSQL processed_events unique event_id (dedup)
   -> commit consumer offset only after DB processing
   -> malformed messages -> DLQ topic (then commit source offset)
```

- The pipeline is **at least once**, not exactly once. A crash between broker acknowledgement and committing `published_at` can create a duplicate Kafka event; the consumer ignores repeated event IDs.
- The publisher holds a PostgreSQL row lock during broker acknowledgement to keep the local-development implementation simple. Production throughput requires a claimed/leased outbox, timeouts, monitoring and backoff.
- Failed sends are retried on the next publisher run/loop. `publish_attempts` tracks attempts; this simple variant has **no exponential backoff or alerting**.
- The audit consumer writes only `processed_events`; it never modifies ledger balances.
- `RiskAlertCreated` remains a future contract until risk alerts are persisted and a separate publisher/topic is implemented. Do not send it to the transfer topic.
- Test with simulated data only. PostgreSQL remains the money source of truth.

## Troubleshooting

- `No module named confluent_kafka`: install `requirements-streaming.txt` in `backend/.venv`.
- `relation processed_events does not exist`: apply migration `0004` to the database pointed to by `DATABASE_URL`.
- Broker refused: `docker compose ps`, `docker exec finguard-redpanda rpk cluster info`; Windows client uses `localhost:19092`.
- No events published: check `outbox_events` for `event_type = TransferPosted` and `published_at IS NULL`; transfers posted *before* the outbox integration have no retroactive outbox event.
- Consumer sends the manual test to DLQ: expected, because its test JSON lacks the mandatory envelope `event_id` and `payload`.
- Always run pytest against `finguard_test`, never the development DB.

## Docs
- https://docs.confluent.io/kafka-clients/python/current/overview.html
- https://docs.redpanda.com/streaming/current/get-started/rpk-quickstart/
- https://docs.sqlalchemy.org/en/20/dialects/postgresql.html
