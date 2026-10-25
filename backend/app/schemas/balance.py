

from uuid import UUID

from pydantic import BaseModel


class BalanceResponse(BaseModel):
    account_id: UUID
    currency: str
    balance_cents: int
