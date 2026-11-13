import concurrent.futures
import uuid
from app.db.models import Account, AccountType, OutboxEvent, User
from app.services.ledger import EntryInput, get_balance, post_transaction
from app.services.limits import check_transfer_limits
from scripts.reconcile_ledger import verify_ledger_reconciliation
from sqlalchemy import func, select


def test_tnd_limits_are_currency_aware(session, world):
    tnd_acc = Account(
        user_id=world["alice"].user_id,
        name="Alice TND",
        account_type=AccountType.CUSTOMER,
        currency="TND",
    )
    session.add(tnd_acc)
    session.commit()
    check_transfer_limits(session, tnd_acc.id, 5_000_000, currency="TND")


def test_atomic_fx_transfer_and_fx_refund(client, session, world):
    eur_bob = Account(
        user_id=world["bob"].user_id,
        name="Bob EUR",
        account_type=AccountType.CUSTOMER,
        currency="EUR",
    )
    sys_usd = session.scalar(select(Account).where(Account.name == "SYSTEM_FX", Account.currency == "USD"))
    sys_eur = session.scalar(select(Account).where(Account.name == "SYSTEM_FX", Account.currency == "EUR"))
    if sys_usd is None:
        sys_usd = Account(name="SYSTEM_FX", account_type=AccountType.SYSTEM, currency="USD")
        session.add(sys_usd)
    if sys_eur is None:
        sys_eur = Account(name="SYSTEM_FX", account_type=AccountType.SYSTEM, currency="EUR")
        session.add(sys_eur)
    session.add(eur_bob)
    session.commit()

    dep = client.post(
        "/deposits",
        headers={"Idempotency-Key": f"fx-dep-{uuid.uuid4()}"},
        json={"account_id": str(world["alice"].id), "amount_cents": 50_000},
    )
    assert dep.status_code == 201

    tr_key = f"fx-tr-{uuid.uuid4()}"
    tr = client.post(
        "/transfers",
        headers={"Idempotency-Key": tr_key},
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(eur_bob.id),
            "amount_cents": 10_000,
            "description": "FX test",
        },
    )
    assert tr.status_code == 201, tr.text
    tx_id = tr.json()["transaction_id"]

    outbox_count = session.scalar(
        select(func.count()).select_from(OutboxEvent).where(OutboxEvent.aggregate_id == uuid.UUID(tx_id))
    )
    assert outbox_count == 1

    mismatch = client.post(
        "/transfers",
        headers={"Idempotency-Key": tr_key},
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(eur_bob.id),
            "amount_cents": 12_000,
            "description": "FX test",
        },
    )
    assert mismatch.status_code == 409

    ref = client.post(
        f"/transfers/{tx_id}/refund",
        headers={"Idempotency-Key": f"fx-ref-{uuid.uuid4()}"},
    )
    assert ref.status_code == 201, ref.text

    dup_ref = client.post(
        f"/transfers/{tx_id}/refund",
        headers={"Idempotency-Key": f"fx-ref-dup-{uuid.uuid4()}"},
    )
    assert dup_ref.status_code == 409

    verify_ledger_reconciliation(session)


def test_concurrent_opposite_transfers_no_deadlock(session, world):
    from app.db.session import SessionLocal
    from app.security.passwords import hash_password

    with SessionLocal() as db:
        u = User(email=f"conc.{uuid.uuid4().hex[:8]}@example.com", full_name="Conc", password_hash=hash_password("StrongPass123!"))
        db.add(u)
        db.flush()
        funding = db.scalar(select(Account).where(Account.name == "SYSTEM_FUNDING", Account.currency == "USD"))
        if funding is None:
            funding = Account(name="SYSTEM_FUNDING", account_type=AccountType.SYSTEM, currency="USD")
            db.add(funding)
            db.flush()
        a = Account(user_id=u.id, name="Conc A", account_type=AccountType.CUSTOMER, currency="USD")
        b = Account(user_id=u.id, name="Conc B", account_type=AccountType.CUSTOMER, currency="USD")
        db.add_all([a, b])
        db.flush()
        post_transaction(db, f"conc-fund-a-{uuid.uuid4()}", [EntryInput(funding.id, -100_000), EntryInput(a.id, 100_000)])
        post_transaction(db, f"conc-fund-b-{uuid.uuid4()}", [EntryInput(funding.id, -100_000), EntryInput(b.id, 100_000)])
        a_id, b_id = a.id, b.id

    def transfer_worker(src, dst, amount, idx):
        with SessionLocal() as db:
            post_transaction(
                db,
                idempotency_key=f"conc-w-{uuid.uuid4()}-{idx}",
                entries=[EntryInput(src, -amount), EntryInput(dst, amount)],
                description="concurrent",
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = []
        for i in range(6):
            if i % 2 == 0:
                futures.append(pool.submit(transfer_worker, a_id, b_id, 1_000, i))
            else:
                futures.append(pool.submit(transfer_worker, b_id, a_id, 1_000, i))
        for f in futures:
            f.result(timeout=15)

    with SessionLocal() as db:
        assert get_balance(db, a_id) + get_balance(db, b_id) == 200_000
        verify_ledger_reconciliation(db)
