# FinGuard Ledger Rules

This document defines the invariants that money must obey in FinGuard.
Every database constraint, service function, and test refers back to these rules.

## Core concepts

- **Account**: a place where money is held (one owner, one currency).
- **Transaction**: one business event (for example, a transfer from A to B).
- **Ledger entry**: one line of a transaction that moves money in or out of one account.
- **Double-entry**: every transaction has at least two entries, and they sum to zero.

## Representation rules

| ID | Rule |
|----|------|
| R1 | Money is stored as an **integer in minor units** (cents). Floats are never used. |
| R2 | Every account has exactly one **currency** (ISO 4217 code, e.g. `USD`). |
| R3 | Amounts on ledger entries are **non-zero**. Positive = credit (money in), negative = debit (money out). |

## Invariants (must always be true)

| ID | Invariant |
|----|-----------|
| I1 | **Balanced transactions**: for every transaction, the sum of its ledger entry amounts is exactly 0. |
| I2 | **Single currency per transaction**: all entries in one transaction use the same currency, and each entry's currency matches its account's currency. |
| I3 | **Immutability**: ledger entries are never updated or deleted. Mistakes are fixed by posting a new reversing transaction. |
| I4 | **Derived balances**: an account's balance equals the sum of its ledger entries. The ledger is the source of truth. |
| I5 | **No overdraft**: a customer account's balance can never go below 0 (system accounts are exempt, see S1). |
| I6 | **Atomicity**: a transaction and all its entries are saved together, or not at all. |
| I7 | **Idempotency**: posting the same transaction twice (same idempotency key) creates it only once. |
| I8 | **Referential integrity**: every entry points to a real transaction and a real account. |
| I9 | **No orphan transactions**: a posted transaction has at least 2 entries. |

## System accounts

| ID | Rule |
|----|------|
| S1 | System accounts (for example `SYSTEM_FUNDING`) are allowed to go negative. They represent money entering or leaving the simulation. |
| S2 | Deposits are modelled as a transfer **from** `SYSTEM_FUNDING` **to** a customer account, so the ledger always balances. |

## Transaction states

`PENDING` -> `POSTED` or `FAILED`.
Only `POSTED` transactions have ledger entries and affect balances. A posted transaction never changes state.

## Worked examples

**Deposit of 50.00 USD to Alice** (amounts in cents):

| Account | Amount |
|---------|--------|
| SYSTEM_FUNDING | -5000 |
| Alice | +5000 |
| **Sum** | **0** ✅ |

**Transfer of 12.50 USD from Alice to Bob:**

| Account | Amount |
|---------|--------|
| Alice | -1250 |
| Bob | +1250 |
| **Sum** | **0** ✅ |

## Out of scope for Phase 1

Multi-currency conversion, fees, interest, and holds are not modelled yet.