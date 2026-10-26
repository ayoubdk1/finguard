
from pydantic import BaseModel, Field


class RiskAssessmentRequest(BaseModel):
    amount_cents: int = Field(gt=0, strict=True)
    transfers_last_10min: int = Field(ge=0, strict=True)
    account_age_minutes: int = Field(ge=0, strict=True)
    failed_transfers_last_hour: int = Field(ge=0, strict=True)
