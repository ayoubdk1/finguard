import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select

from app.db.models import (
    LoginHistory,
    User,
)
from app.db.session import SessionLocal
from app.schemas.auth import (
    AdminCreateUserRequest,
    AdminResetPasswordRequest,
    AdminUpdateUserRequest,
    AdminUserResponse,
    LoginHistoryItem,
    SessionItem,
    SessionListResponse,
)
from app.security.dependencies import get_current_user
from app.security.passwords import hash_password
from app.security.permissions import Permission, has_permission
from app.security.tokens import (
    get_active_sessions_for_user,
    revoke_all_user_sessions,
    revoke_session_by_id,
)

logger = logging.getLogger("finguard.security")

router = APIRouter()



@router.get(
    "/admin/users",
    response_model=list[AdminUserResponse],
    status_code=status.HTTP_200_OK,
)
def admin_list_users(current_user: User = Depends(get_current_user)):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        users = session.scalars(
            select(User).order_by(User.created_at.desc())
        ).all()
        return users


@router.post(
    "/admin/users",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_user(
    payload: AdminCreateUserRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        existing = session.scalar(
            select(User).where(User.email == payload.email)
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        user = User(
            email=payload.email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
            role=payload.role,
            status=payload.status,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@router.patch(
    "/admin/users/{user_id}",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
)
def admin_update_user(
    user_id: UUID,
    payload: AdminUpdateUserRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.role is not None:
            user.role = payload.role
        if payload.status is not None:
            user.status = payload.status
            if payload.status != "ACTIVE":
                revoke_all_user_sessions(session, user.id)

        session.commit()
        session.refresh(user)
        return user


@router.post(
    "/admin/users/{user_id}/reset-password",
    status_code=status.HTTP_200_OK,
)
def admin_reset_user_password(
    user_id: UUID,
    payload: AdminResetPasswordRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        user.password_hash = hash_password(payload.new_password)
        revoke_all_user_sessions(session, user.id)
        session.commit()
        return {"status": "password_reset_by_admin"}


@router.get(
    "/admin/users/{user_id}/login-history",
    response_model=list[LoginHistoryItem],
    status_code=status.HTTP_200_OK,
)
def admin_get_login_history(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        rows = session.scalars(
            select(LoginHistory)
            .where(LoginHistory.user_id == user_id)
            .order_by(LoginHistory.created_at.desc())
            .limit(50)
        ).all()
        return rows


@router.get(
    "/admin/users/{user_id}/sessions",
    response_model=SessionListResponse,
    status_code=status.HTTP_200_OK,
)
def admin_list_user_sessions(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        active_tokens = get_active_sessions_for_user(session, user_id)
        items = [SessionItem.model_validate(tok) for tok in active_tokens]
        return SessionListResponse(sessions=items, total_active=len(items))


@router.delete(
    "/admin/users/{user_id}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def admin_revoke_user_session(
    user_id: UUID,
    session_id: UUID,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        revoked = revoke_session_by_id(session, session_id, user_id)
        if not revoked:
            raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
