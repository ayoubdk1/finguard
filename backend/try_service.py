import uuid

from app.db.models import Account, AccountType, User
from app.db.session import SessionLocal
from app.services.ledger import (
    EntryInput,
    InsufficientFunds,
    get_balance,
    post_transaction,
)

run = uuid.uuid4().hex[:8]

with SessionLocal() as s:
    ua = User(email=f"alice-{run}@test.local", full_name="Alice")
    ub = User(email=f"bob-{run}@test.local", full_name="Bob")
    s.add_all([ua, ub])
    s.flush()
    funding = Account(name="SYSTEM_FUNDING", account_type=AccountType.SYSTEM, currency="USD")
    alice = Account(user_id=ua.id, name="Alice", account_type=AccountType.CUSTOMER, currency="USD")
    bob = Account(user_id=ub.id, name="Bob", account_type=AccountType.CUSTOMER, currency="USD")
    s.add_all([funding, alice, bob])
    s.commit()
    f_id, a_id, b_id = funding.id, alice.id, bob.id

    def show(label):
        print(
            f"{label:<28} funding={get_balance(s, f_id):>6} "
            f"alice={get_balance(s, a_id):>6} bob={get_balance(s, b_id):>6}"
        )

    dep = post_transaction(
        s, f"dep-{run}", [EntryInput(f_id, -5000), EntryInput(a_id, 5000)], "deposit"
    )
    show("after deposit 5000")

    post_transaction(
        s, f"tr-{run}", [EntryInput(a_id, -1250), EntryInput(b_id, 1250)], "transfer"
    )
    show("after transfer 1250")

    again = post_transaction(
        s, f"dep-{run}", [EntryInput(f_id, -5000), EntryInput(a_id, 5000)], "deposit"
    )
    print("replay returns same tx:", again.id == dep.id)
    show("after replay (no change)")

    try:
        post_transaction(
            s, f"big-{run}", [EntryInput(a_id, -999999), EntryInput(b_id, 999999)]
        )
    except InsufficientFunds as e:
        print("overdraft rejected:", e)
    show("after rejected overdraft") 