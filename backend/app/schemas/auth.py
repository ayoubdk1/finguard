from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


# ============================================
# REGISTRATION REQUEST
# ============================================

class RegisterRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    full_name: str = Field(
        min_length=1,
        max_length=255
    )

    password: str = Field(
        min_length=12,
        max_length=128
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = str(value).strip().lower()

        if len(normalized) > 255:
            raise ValueError("Email is too long")

        return normalized

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("Full name cannot be empty")

        return normalized


# ============================================
# REGISTRATION RESPONSE
# ============================================

class RegisterResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: str
    created_at: datetime


# ============================================
# LOGIN REQUEST & TOKEN RESPONSE
# ============================================

class LoginRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(
        min_length=1,
        max_length=128
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return str(value).strip().lower()


class TokenResponse(BaseModel):

    access_token: str
    token_type: str = "bearer"
