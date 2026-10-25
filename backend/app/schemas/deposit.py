
from uuid import UUID

from pydantic import BaseModel, Field


class DepositCreate(BaseModel):
    account_id: UUID
    amount_cents: int = Field(gt=0)
    description: str = Field(
        default="Simulated deposit",
        max_length=255
    )
