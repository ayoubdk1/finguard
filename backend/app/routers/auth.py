import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import LoginHistory, MfaTokenState, User
from app.db.session import SessionLocal
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    MfaBackupCodesResponse,
    MfaDisableRequest,
    MfaLoginRequest,
    MfaSetupRequest,
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
    record_failed_login_and_check_spray,
)
from app.security.tokens import (
    create_access_token,
    create_mfa_token,
    create_password_reset_token,
    get_active_sessions_for_user,
    get_refresh_token_family_id,
    issue_refresh_token,
    revoke_access_token,
    revoke_all_user_sessions,
    revoke_refresh_token,
    revoke_session_by_id,
    rotate_refresh_token,
    verify_access_token_claims,
    verify_mfa_token_with_jti,
    verify_password_reset_token,
)
from app.services.audit import get_client_ip, get_request_id, record_audit_event
from app.services.email import get_email_sender

logger = logging.getLogger("finguard.security")
router = APIRouter()
MFA_LOCKOUT_MINUTES = 15
_DUMMY_PASSWORD_HASH = hash_password("FinGuard-Timing-Dummy-Secret!2026")
MFA_MAX_FAILED = 5
REFRESH_COOKIE_NAME = "finguard_refresh_token"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    is_prod = os.getenv("FINGUARD_ENV", "development").lower() == "production"
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="strict",
        secure=is_prod,
        max_age=7 * 24 * 3600,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    is_prod = os.getenv("FINGUARD_ENV", "development").lower() == "production"
    response.delete_cookie(key=REFRESH_COOKIE_NAME, httponly=True, samesite="strict", secure=is_prod, path="/")


@router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_403_FORBIDDEN)
def register_user(payload: RegisterRequest):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Public registration is disabled. Contact an administrator.")


@router.post("/auth/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login_user(request: Request, response: Response, payload: LoginRequest):
    check_login_rate_limit(request, email=payload.email)
    client_ip = extract_client_ip(request)
    user_agent = request.headers.get("user-agent")
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == payload.email))
        candidate_hash = user.password_hash if (user is not None and user.password_hash) else _DUMMY_PASSWORD_HASH
        password_ok = verify_password(payload.password, candidate_hash)
        if user is None or not user.password_hash or not password_ok:
            session.add(LoginHistory(user_id=user.id if user else None, email=payload.email, ip_address=client_ip[:45] if client_ip else None, user_agent=user_agent[:255] if user_agent else None, success=False, failure_reason="Invalid credentials"))
            session.commit()
            record_failed_login_and_check_spray(payload.email)
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
        _set_refresh_cookie(response, refresh_token)
        return TokenResponse(access_token=token, refresh_token=refresh_token)


@router.post("/auth/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def refresh_access_token(request: Request, response: Response, payload: RefreshRequest | None = Body(default=None)):
    raw_token = (payload.refresh_token if payload and payload.refresh_token else None) or request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token", headers={"WWW-Authenticate": "Bearer"})
    with SessionLocal() as session:
        family_id = get_refresh_token_family_id(session, raw_token)
        check_refresh_rate_limit(str(family_id) if family_id else hashlib.sha256(raw_token.encode()).hexdigest()[:16])
        from app.db.models import RefreshToken
        from app.security.tokens import hash_refresh_token
        old_tok = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token)))
        orig_auth_time = int((old_tok.created_at.replace(tzinfo=timezone.utc) if old_tok and old_tok.created_at.tzinfo is None else old_tok.created_at).timestamp()) if old_tok and old_tok.created_at else int(datetime.now(timezone.utc).timestamp())
        try:
            user_id, new_refresh = rotate_refresh_token(session, raw_token, user_agent=request.headers.get("user-agent"), ip_address=extract_client_ip(request))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
        _set_refresh_cookie(response, new_refresh)
        return TokenResponse(access_token=create_access_token(user_id, auth_time=orig_auth_time), refresh_token=new_refresh)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_user(request: Request, response: Response, payload: LogoutRequest | None = Body(default=None)):
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            claims = verify_access_token_claims(auth.split(" ", 1)[1].strip())
            revoke_access_token(str(claims["jti"]), float(claims["exp"]))
        except ValueError:
            pass
    raw_token = (payload.refresh_token if payload and payload.refresh_token else None) or request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_token:
        with SessionLocal() as session:
            revoke_refresh_token(session, raw_token)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/auth/mfa/setup", response_model=MfaSetupResponse, status_code=status.HTTP_200_OK)
def mfa_setup(payload: MfaSetupRequest, current_user: User = Depends(get_current_user), _step_up: None = Depends(require_recent_login)):
    with SessionLocal() as session:
        user = session.get(User, current_user.id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if not user.password_hash or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid current password")
        if user.mfa_enabled:
            raise HTTPException(status_code=400, detail="MFA is already enabled")
        secret = generate_mfa_secret()
        user.mfa_secret = encrypt_mfa_secret(secret)
        user.mfa_key_id = get_active_mfa_key_id()
        session.commit()
        return MfaSetupResponse(secret=secret, otpauth_uri=generate_totp_uri(secret, user.email))


@router.post("/auth/mfa/enable", status_code=status.HTTP_200_OK)
def mfa_enable(request: Request, payload: MfaVerifyRequest, current_user: User = Depends(get_current_user), _step_up: None = Depends(require_recent_login)):
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
        record_audit_event(session, action="MFA_ENABLED", resource_type="USER", resource_id=user.id, actor_id=user.id, ip_address=get_client_ip(request), request_id=get_request_id(request))
        user.mfa_failed_attempts = 0
        user.mfa_locked_until = None
        user.mfa_backup_codes = [hash_backup_code(c) for c in plain_codes]
        session.commit()
        return {"status": "MFA successfully enabled", "backup_codes": plain_codes}


@router.post("/auth/mfa/disable", status_code=status.HTTP_200_OK)
def mfa_disable(request: Request, payload: MfaDisableRequest, current_user: User = Depends(get_current_user), _step_up: None = Depends(require_recent_login)):
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
        record_audit_event(session, action="MFA_DISABLED", resource_type="USER", resource_id=user.id, actor_id=user.id, ip_address=get_client_ip(request), request_id=get_request_id(request))
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
def mfa_login(request: Request, response: Response, payload: MfaLoginRequest):
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
        session.execute(
            pg_insert(MfaTokenState)
            .values(jti=jti, user_id=user.id, failed_attempts=0, expires_at=now + timedelta(minutes=5))
            .on_conflict_do_nothing(index_elements=["jti"])
        )
        tok_state = session.scalar(select(MfaTokenState).where(MfaTokenState.jti == jti).with_for_update())
        if tok_state is None:
            raise HTTPException(status_code=401, detail="Invalid MFA token")
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
        _set_refresh_cookie(response, refresh_token)
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



@router.post("/auth/change-password", status_code=status.HTTP_200_OK)
def change_password(request: Request, payload: ChangePasswordRequest, current_user: User = Depends(get_current_user)):
    try:
        validate_password_policy(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different from current password")
    with SessionLocal() as session:
        user = session.get(User, current_user.id)
        if user is None or not user.password_hash or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        user.password_hash = hash_password(payload.new_password)
        record_audit_event(session, action="PASSWORD_CHANGED", resource_type="USER", resource_id=user.id, actor_id=user.id, ip_address=get_client_ip(request), request_id=get_request_id(request))
        revoke_all_user_sessions(session, user.id)
        session.commit()
        return {"status": "password_changed"}


@router.get("/auth/me", response_model=RegisterResponse, status_code=status.HTTP_200_OK)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user
