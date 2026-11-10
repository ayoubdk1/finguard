
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
    # Multi-currency FX fields (optional)
    is_fx: bool = False
    target_currency: str | None = None
    converted_amount_cents: int | None = None
    fee_cents: int | None = None
    exchange_rate: float | None = None
