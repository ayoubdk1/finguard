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
    refresh_token: str | None = None
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_token: str | None = None


class RefreshRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=16, max_length=256)


class LogoutRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=16, max_length=256)
# ============================================
# ACTIVE SESSIONS
# ============================================

class SessionItem(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    user_agent: str | None = None
    ip_address: str | None = None
    created_at: datetime
    expires_at: datetime


class SessionListResponse(BaseModel):

    sessions: list[SessionItem]
    total_active: int

# ============================================
# MULTI-FACTOR AUTHENTICATION (TOTP)
# ============================================

class MfaSetupResponse(BaseModel):

    secret: str
    otpauth_uri: str
    issuer: str = "FinGuard"


class MfaVerifyRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=6)


class MfaLoginRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    mfa_token: str
    code: str = Field(min_length=6, max_length=6)


# ============================================
# PASSWORD RESET (FORGOT / RESET PASSWORD)
# ============================================

class ForgotPasswordRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return str(value).strip().lower()


class ForgotPasswordResponse(BaseModel):

    message: str
    reset_token: str | None = None


class ResetPasswordRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    reset_token: str = Field(min_length=16, max_length=1024)
    new_password: str = Field(min_length=12, max_length=128)
