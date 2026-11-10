
from uuid import UUID

from pydantic import BaseModel, Field


class TransferCreate(BaseModel):
    source_account_id: UUID
    destination_account_id: UUID
    amount_cents: int = Field(gt=0, strict=True)
    description: str = Field(
        default="Simulated transfer",
        max_length=255
    )

class TransferResponse(BaseModel):
    transaction_id: str
    status: str
    amount_cents: int
    source_account_id: str
    destination_account_id: str
    created_at: str
