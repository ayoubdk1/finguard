import concurrent.futures
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select

from app.db.models import Account, AccountBalance, AccountType, LedgerEntry, User
from app.db.session import SessionLocal
from app.main import app
from app.security.dependencies import get_current_user
from app.services.ledger import (
    EntryInput,
    InsufficientFunds,
    get_balance,
    post_transaction,
    verify_balance_projections,
)


def test_p16_concurrent_overdraft_prevented_and_projections_match(committed_world):
    funding_id = committed_world["funding_id"]
    alice_id = committed_world["alice_id"]
    bob_id = committed_world["bob_id"]

    with SessionLocal() as db:
        post_transaction(
            session=db,
            idempotency_key=str(uuid.uuid4()),
            idempotency_scope="p16:seed",
            request_hash=uuid.uuid4().hex,
            entries=[EntryInput(funding_id, -10_000), EntryInput(alice_id, 10_000)],
            description="seed 100.00 USD",
        )

    def attempt_transfer(idx: int) -> str:
        with SessionLocal() as db:
            try:
                post_transaction(
                    session=db,
                    idempotency_key=f"conc-{uuid.uuid4()}",
                    idempotency_scope=f"p16:conc:{idx}",
                    request_hash=uuid.uuid4().hex,
                    entries=[EntryInput(alice_id, -3_000), EntryInput(bob_id, 3_000)],
                    description=f"parallel {idx}",
                )
                return "OK"
            except InsufficientFunds:
                return "INSUFFICIENT"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt_transfer, range(8)))

    assert results.count("OK") == 3
    assert results.count("INSUFFICIENT") == 5

    with SessionLocal() as db:
        alice_bal = get_balance(db, alice_id)
        bob_bal = get_balance(db, bob_id)
        funding_bal = get_balance(db, funding_id)
        assert alice_bal == 1_000
        assert bob_bal == 9_000
        assert alice_bal + bob_bal + funding_bal == 0
        assert db.get(AccountBalance, alice_id).balance == 1_000
        assert db.get(AccountBalance, bob_id).balance == 9_000
        assert verify_balance_projections(db) == []


def test_p16_concurrent_refund_single_winner_and_zero_500s(committed_world):
    funding_id = committed_world["funding_id"]
    alice_id = committed_world["alice_id"]
    bob_id = committed_world["bob_id"]
    bob_user = committed_world["bob_user"]

    with SessionLocal() as db:
        post_transaction(
            session=db,
            idempotency_key=str(uuid.uuid4()),
            idempotency_scope="p16:refseed",
            request_hash=uuid.uuid4().hex,
            entries=[EntryInput(funding_id, -20_000), EntryInput(alice_id, 20_000)],
            description="seed for refund",
        )
        orig_tx = post_transaction(
            session=db,
            idempotency_key=str(uuid.uuid4()),
            idempotency_scope="p16:reforig",
            request_hash=uuid.uuid4().hex,
            entries=[EntryInput(alice_id, -5_000), EntryInput(bob_id, 5_000)],
            description="transfer to refund",
        )
        orig_tx_id = orig_tx.id

    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: bob_user
    try:
        with TestClient(app) as tc:
            def do_refund(_i: int) -> int:
                return tc.post(
                    f"/transfers/{orig_tx_id}/refund",
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                ).status_code

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                statuses = list(pool.map(do_refund, range(6)))

        assert 500 not in statuses
        assert statuses.count(201) == 1
        assert statuses.count(409) == 5

        with SessionLocal() as db:
            assert get_balance(db, alice_id) == 20_000
            assert get_balance(db, bob_id) == 0
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


@settings(max_examples=15, deadline=None)
@given(
    ops=st.lists(
        st.tuples(
            st.sampled_from(["deposit", "transfer_ab", "transfer_ba"]),
            st.integers(min_value=1, max_value=5000),
        ),
        min_size=1,
        max_size=12,
    )
)
def test_p16_hypothesis_stateful_ledger_invariants(ops):
    run = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        u1 = User(email=f"hyp1-{run}@example.com", full_name="H1", role="CUSTOMER", status="ACTIVE")
        u2 = User(email=f"hyp2-{run}@example.com", full_name="H2", role="CUSTOMER", status="ACTIVE")
        db.add_all([u1, u2])
        db.flush()
        funding = Account(name=f"SYSTEM_HYP_{run}", account_type=AccountType.SYSTEM, currency="USD")
        a = Account(user_id=u1.id, name="HypA", account_type=AccountType.CUSTOMER, currency="USD")
        b = Account(user_id=u2.id, name="HypB", account_type=AccountType.CUSTOMER, currency="USD")
        db.add_all([funding, a, b])
        db.commit()

        for idx, (kind, amount) in enumerate(ops):
            try:
                if kind == "deposit":
                    entries = [EntryInput(funding.id, -amount), EntryInput(a.id, amount)]
                elif kind == "transfer_ab":
                    entries = [EntryInput(a.id, -amount), EntryInput(b.id, amount)]
                else:
                    entries = [EntryInput(b.id, -amount), EntryInput(a.id, amount)]
                post_transaction(
                    session=db,
                    idempotency_key=f"hyp-{run}-{idx}",
                    idempotency_scope=f"hyp:{run}",
                    request_hash=uuid.uuid4().hex,
                    entries=entries,
                    description=kind,
                )
            except InsufficientFunds:
                pass

        bal_a = get_balance(db, a.id)
        bal_b = get_balance(db, b.id)
        bal_f = get_balance(db, funding.id)
        assert bal_a >= 0
        assert bal_b >= 0
        assert bal_a + bal_b + bal_f == 0

        total_sum = db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.account_id.in_([funding.id, a.id, b.id])
            )
        )
        assert int(total_sum or 0) == 0

        proj_a = db.get(AccountBalance, a.id)
        proj_b = db.get(AccountBalance, b.id)
        if proj_a is not None:
            assert proj_a.balance == bal_a
        if proj_b is not None:
            assert proj_b.balance == bal_b


def test_p16_governance_files_present():
    root = Path(__file__).resolve().parents[2]
    for rel in [
        ".github/CODEOWNERS",
        ".github/pull_request_template.md",
        "SECURITY.md",
        "CHANGELOG.md",
        "docs/stride-threat-model.md",
    ]:
        p = root / rel
        assert p.exists() and p.stat().st_size > 50, f"Missing or empty {rel}"
