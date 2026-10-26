
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.db.models import OutboxEvent


def enqueue_transfer_posted(
    session: Session,
    *,
    transaction_id: UUID,
    source_account_id: UUID,
    destination_account_id: UUID,
    amount_cents: int,
    currency: str,
    correlation_id: UUID | None = None,
) -> OutboxEvent:

    if type(amount_cents) is not int or amount_cents <= 0:
        raise ValueError("Amount must be a positive integer")

    if (
        not isinstance(currency, str)
        or len(currency) != 3
        or not currency.isalpha()
    ):
        raise ValueError("Currency must be a 3-letter code")

    event = OutboxEvent(
        id=uuid4(),
        aggregate_id=transaction_id,
        correlation_id=correlation_id or uuid4(),
        event_type="TransferPosted",
        event_version=1,
        payload={
            "transaction_id": str(transaction_id),
            "source_account_id": str(source_account_id),
            "destination_account_id": str(destination_account_id),
            "amount_cents": amount_cents,
            "currency": currency.upper(),
        },
        publish_attempts=0,
    )

    session.add(event)

    # No commit here!
    # The calling service controls the database transaction.
    return event
