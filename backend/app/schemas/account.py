
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AccountCreate(BaseModel):
    user_id: UUID
    name: str = Field(min_length=1, max_length=100)
    currency: str = Field(default="TND", pattern=r"^[A-Z]{3}$")


class AccountResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    account_type: str
    currency: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
