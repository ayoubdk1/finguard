import hashlib
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.db.models import LoginHistory, MfaTokenState, User
from app.db.session import SessionLocal
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    MfaBackupCodesResponse,
    MfaDisableRequest,
    MfaLoginRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SessionItem,
    SessionListResponse,
    TokenResponse,
)
from app.security.dependencies import get_current_user, require_recent_login
from app.security.mfa import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_backup_codes,
    generate_mfa_secret,
    generate_totp_uri,
    get_active_mfa_key_id,
    hash_backup_code,
    verify_and_consume_backup_code,
    verify_totp_with_step,
)
from app.security.passwords import hash_password, validate_password_policy, verify_password
from app.security.rate_limit import (
    check_login_rate_limit,
    check_mfa_rate_limit,
    check_refresh_rate_limit,
    extract_client_ip,
)
from app.security.tokens import (
    create_access_token,
    create_mfa_token,
    create_password_reset_token,
    get_active_sessions_for_user,
    get_refresh_token_family_id,
    issue_refresh_token,
    revoke_all_user_sessions,
    revoke_refresh_token,
    revoke_session_by_id,
    rotate_refresh_token,
    verify_mfa_token_with_jti,
    verify_password_reset_token,
)
from app.services.email import get_email_sender

logger = logging.getLogger("finguard.security")
router = APIRouter()
MFA_LOCKOUT_MINUTES = 15
MFA_MAX_FAILED = 5


@router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_403_FORBIDDEN)
def register_user(payload: RegisterRequest):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Public registration is disabled. Contact an administrator.")


@router.post("/auth/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login_user(request: Request, payload: LoginRequest):
    check_login_rate_limit(request, email=payload.email)
    client_ip = extract_client_ip(request)
    user_agent = request.headers.get("user-agent")
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == payload.email))
        if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
            session.add(LoginHistory(user_id=user.id if user else None, email=payload.email, ip_address=client_ip[:45] if client_ip else None, user_agent=user_agent[:255] if user_agent else None, success=False, failure_reason="Invalid credentials"))
            session.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
        if getattr(user, "status", "ACTIVE") != "ACTIVE":
            session.add(LoginHistory(user_id=user.id, email=user.email, ip_address=client_ip[:45] if client_ip else None, user_agent=user_agent[:255] if user_agent else None, success=False, failure_reason=f"Account {user.status.lower()}"))
            session.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active. Contact an administrator.")
        if user.mfa_enabled:
            session.add(LoginHistory(user_id=user.id, email=user.email, ip_address=client_ip[:45] if client_ip else None, user_agent=user_agent[:255] if user_agent else None, success=True, failure_reason="MFA pending"))
            session.commit()
            return TokenResponse(access_token="", mfa_required=True, mfa_token=create_mfa_token(user.id))
        token = create_access_token(user.id)
        refresh_token, _ = issue_refresh_token(session, user.id, user_agent=user_agent, ip_address=client_ip)
        session.add(LoginHistory(user_id=user.id, email=user.email, ip_address=client_ip[:45] if client_ip else None, user_agent=user_agent[:255] if user_agent else None, success=True))
        session.commit()
        return TokenResponse(access_token=token, refresh_token=refresh_token)


@router.post("/auth/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def refresh_access_token(request: Request, payload: RefreshRequest):
    with SessionLocal() as session:
        family_id = get_refresh_token_family_id(session, payload.refresh_token)
        check_refresh_rate_limit(str(family_id) if family_id else hashlib.sha256(payload.refresh_token.encode()).hexdigest()[:16])
        try:
            user_id, new_refresh = rotate_refresh_token(session, payload.refresh_token, user_agent=request.headers.get("user-agent"), ip_address=extract_client_ip(request))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
        return TokenResponse(access_token=create_access_token(user_id), refresh_token=new_refresh)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_user(payload: LogoutRequest):
    with SessionLocal() as session:
        revoke_refresh_token(session, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/mfa/setup", response_model=MfaSetupResponse, status_code=status.HTTP_200_OK)
def mfa_setup(current_user: User = Depends(get_current_user), _step_up: None = Depends(require_recent_login)):
    with SessionLocal() as session:
        user = session.get(User, current_user.id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user.mfa_enabled:
            raise HTTPException(status_code=400, detail="MFA is already enabled")
        secret = generate_mfa_secret()
        user.mfa_secret = encrypt_mfa_secret(secret)
        user.mfa_key_id = get_active_mfa_key_id()
        session.commit()
        return MfaSetupResponse(secret=secret, otpauth_uri=generate_totp_uri(secret, user.email))


@router.post("/auth/mfa/enable", status_code=status.HTTP_200_OK)
def mfa_enable(payload: MfaVerifyRequest, current_user: User = Depends(get_current_user), _step_up: None = Depends(require_recent_login)):
    with SessionLocal() as session:
        user = session.get(User, current_user.id)
        if user is None or not user.mfa_secret:
            raise HTTPException(status_code=400, detail="MFA setup has not been initiated")
        if user.mfa_enabled:
            raise HTTPException(status_code=400, detail="MFA is already enabled")
        step = verify_totp_with_step(decrypt_mfa_secret(user.mfa_secret), payload.code, last_step=user.mfa_last_totp_step)
        if step is None:
            raise HTTPException(status_code=400, detail="Invalid verification code")
        plain_codes = generate_backup_codes(10)
        user.mfa_enabled = True
        user.mfa_last_totp_step = step
        user.mfa_failed_attempts = 0
        user.mfa_locked_until = None
        user.mfa_backup_codes = [hash_backup_code(c) for c in plain_codes]
        session.commit()
        return {"status": "MFA successfully enabled", "backup_codes": plain_codes}


@router.post("/auth/mfa/disable", status_code=status.HTTP_200_OK)
def mfa_disable(payload: MfaDisableRequest, current_user: User = Depends(get_current_user), _step_up: None = Depends(require_recent_login)):
    with SessionLocal() as session:
        user = session.get(User, current_user.id)
        if user is None or not user.mfa_enabled or not user.mfa_secret:
            raise HTTPException(status_code=400, detail="MFA is not enabled")
        if not user.password_hash or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid password")
        step = verify_totp_with_step(decrypt_mfa_secret(user.mfa_secret), payload.code, last_step=user.mfa_last_totp_step)
        if step is None:
            raise HTTPException(status_code=400, detail="Invalid verification code")
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_key_id = None
        user.mfa_last_totp_step = None
        user.mfa_backup_codes = None
        user.mfa_failed_attempts = 0
        user.mfa_locked_until = None
        session.commit()
        return {"status": "MFA successfully disabled"}


@router.post("/auth/mfa/backup-codes/regenerate", response_model=MfaBackupCodesResponse, status_code=status.HTTP_200_OK)
def mfa_regenerate_backup_codes(current_user: User = Depends(get_current_user), _step_up: None = Depends(require_recent_login)):
    with SessionLocal() as session:
        user = session.get(User, current_user.id)
        if user is None or not user.mfa_enabled:
            raise HTTPException(status_code=400, detail="MFA is not enabled")
        plain_codes = generate_backup_codes(10)
        user.mfa_backup_codes = [hash_backup_code(c) for c in plain_codes]
        session.commit()
        return MfaBackupCodesResponse(backup_codes=plain_codes)


@router.post("/auth/mfa/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def mfa_login(request: Request, payload: MfaLoginRequest):
    try:
        user_id, jti = verify_mfa_token_with_jti(payload.mfa_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    check_mfa_rate_limit(str(user_id))
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None or not user.mfa_enabled or not user.mfa_secret:
            raise HTTPException(status_code=400, detail="MFA not active for this account")
        if user.mfa_locked_until is not None:
            locked_until = user.mfa_locked_until if user.mfa_locked_until.tzinfo else user.mfa_locked_until.replace(tzinfo=timezone.utc)
            if locked_until > now:
                raise HTTPException(status_code=423, detail="Account MFA is temporarily locked due to failed attempts")
        tok_state = session.get(MfaTokenState, jti)
        if tok_state is None:
            tok_state = MfaTokenState(jti=jti, user_id=user.id, failed_attempts=0, expires_at=now + timedelta(minutes=5))
            session.add(tok_state)
            session.flush()
        if tok_state.used_at is not None:
            raise HTTPException(status_code=401, detail="MFA token has already been used")
        if tok_state.failed_attempts >= MFA_MAX_FAILED:
            raise HTTPException(status_code=423, detail="MFA token locked due to too many failed attempts")

        secret = decrypt_mfa_secret(user.mfa_secret)
        step = verify_totp_with_step(secret, payload.code, last_step=user.mfa_last_totp_step)
        used_backup = False
        if step is None:
            ok_backup, remaining = verify_and_consume_backup_code(payload.code, list(user.mfa_backup_codes or []))
            if ok_backup:
                used_backup = True
                user.mfa_backup_codes = remaining
        if step is None and not used_backup:
            tok_state.failed_attempts += 1
            user.mfa_failed_attempts += 1
            if user.mfa_failed_attempts >= MFA_MAX_FAILED:
                user.mfa_locked_until = now + timedelta(minutes=MFA_LOCKOUT_MINUTES)
            session.commit()
            raise HTTPException(status_code=401, detail="Invalid MFA code")

        tok_state.used_at = now
        if step is not None:
            user.mfa_last_totp_step = step
        user.mfa_failed_attempts = 0
        user.mfa_locked_until = None
        token = create_access_token(user.id)
        refresh_token, _ = issue_refresh_token(session, user.id, user_agent=request.headers.get("user-agent"), ip_address=extract_client_ip(request))
        session.commit()
        return TokenResponse(access_token=token, refresh_token=refresh_token)


@router.get("/auth/sessions", response_model=SessionListResponse, status_code=status.HTTP_200_OK)
def list_active_sessions(current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        active_tokens = get_active_sessions_for_user(session, current_user.id)
        items = [SessionItem.model_validate(tok) for tok in active_tokens]
        return SessionListResponse(sessions=items, total_active=len(items))


@router.delete("/auth/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: UUID, current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        if not revoke_session_by_id(session, session_id, current_user.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/forgot-password", response_model=ForgotPasswordResponse, status_code=status.HTTP_200_OK)
def forgot_password(request: Request, payload: ForgotPasswordRequest):
    check_login_rate_limit(request, email=payload.email)
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == payload.email))
        if user is not None and user.password_hash:
            reset_token = create_password_reset_token(user_id=user.id, email=user.email, current_password_hash=user.password_hash)
            get_email_sender().send_password_reset(user.email, reset_token)
        return ForgotPasswordResponse(message="If an account matches that email, a password reset link has been sent.")


@router.post("/auth/reset-password", status_code=status.HTTP_200_OK)
def reset_password(request: Request, payload: ResetPasswordRequest):
    check_login_rate_limit(request)
    try:
        validate_password_policy(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    try:
        claims = verify_password_reset_token(payload.reset_token)
        user_id = UUID(str(claims["sub"]))
    except (jwt.InvalidTokenError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired password reset token") from exc
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None or not user.password_hash:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired password reset token")
        expected_fgp = hashlib.sha256(user.password_hash.encode("utf-8")).hexdigest()[:16]
        if claims.get("pwd_fgp") != expected_fgp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password reset token has already been used")
        user.password_hash = hash_password(payload.new_password)
        revoke_all_user_sessions(session, user.id)
        session.commit()
        return {"status": "password_reset_success"}


@router.get("/auth/me", response_model=RegisterResponse, status_code=status.HTTP_200_OK)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user
