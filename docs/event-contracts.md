
# FinGuard — Event Contracts

## Architecture

FinGuard uses PostgreSQL as the source of truth.
Redpanda will transport asynchronous events.

The initial events use JSON and version 1.

## Event 1: TransferPosted

Topic: finguard.transfers.posted.v1

Triggered after a simulated customer transfer is
successfully posted and committed.

Example payload:

{
  "event_id": "550e8400-e29b-41d4-a716-446655440001",
  "event_type": "TransferPosted",
  "event_version": 1,
  "occurred_at": "2026-10-26T18:00:00Z",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440002",
  "payload": {
    "transaction_id": "550e8400-e29b-41d4-a716-446655440003",
    "source_account_id": "550e8400-e29b-41d4-a716-446655440004",
    "destination_account_id": "550e8400-e29b-41d4-a716-446655440005",
    "amount_cents": 2000,
    "currency": "TND"
  }
}

## Event 2: RiskAlertCreated

Topic: finguard.risk.alerts.v1

Planned for when persistent risk alerts are implemented.

Example payload:

{
  "event_id": "550e8400-e29b-41d4-a716-446655440011",
  "event_type": "RiskAlertCreated",
  "event_version": 1,
  "occurred_at": "2026-10-26T18:00:00Z",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440012",
  "payload": {
    "alert_id": "550e8400-e29b-41d4-a716-446655440013",
    "transaction_id": "550e8400-e29b-41d4-a716-446655440003",
    "risk_score": 85,
    "decision": "REVIEW",
    "reason_codes": [
      "LARGE_AMOUNT",
      "HIGH_VELOCITY",
      "NEW_ACCOUNT"
    ]
  }
}

## Event Rules

1. Each event has a unique event_id.
2. Each event contains an event_version.
3. Timestamps are expressed in UTC.
4. Money uses integer cents in this simulation.
5. No passwords or personal customer data in events.
6. Consumers must handle duplicate event delivery.
7. Failed transactions must not produce TransferPosted.
8. Event delivery must not create extra ledger entries.
9. Use a transactional outbox for reliable publishing.
10. RiskAlertCreated requires persisted alerts first.
