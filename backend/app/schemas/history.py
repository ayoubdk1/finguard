
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TransactionHistoryItem(BaseModel):
    transaction_id: UUID
    created_at: datetime
    description: str
    status: str
    amount_cents: int
    currency: str


class TransactionHistoryResponse(BaseModel):
    account_id: UUID
    transactions: list[TransactionHistoryItem]
