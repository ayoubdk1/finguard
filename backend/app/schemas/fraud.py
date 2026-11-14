from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FraudAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID | None = None
    account_id: UUID
    risk_score: float
    reasons: str
    status: str
    analyst_id: UUID | None = None
    analyst_notes: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class FraudResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(APPROVED|BLOCKED)$")
    analyst_notes: str = Field(min_length=3, max_length=1000)
