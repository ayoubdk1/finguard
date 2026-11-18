import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.db.models import (
    ApprovalRequest,
    AuditLog,
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
from app.services.audit import get_client_ip, get_request_id, record_audit_event

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
    request: Request,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        demoting = payload.role is not None and payload.role != "ADMIN"
        disabling = payload.status is not None and payload.status != "ACTIVE"
        if user.id == current_user.id and (demoting or disabling):
            raise HTTPException(status_code=409, detail="Cannot demote or disable your own admin account")
        if user.role == "ADMIN" and user.status == "ACTIVE" and (demoting or disabling):
            active_admins = int(session.scalar(select(func.count()).select_from(User).where(User.role == "ADMIN", User.status == "ACTIVE")) or 0)
            if active_admins <= 1:
                raise HTTPException(status_code=409, detail="Cannot demote or disable the last active admin")
        old_role, old_status = user.role, user.status
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.role is not None:
            user.role = payload.role
        if payload.status is not None:
            user.status = payload.status
            if payload.status != "ACTIVE":
                revoke_all_user_sessions(session, user.id)
        if payload.role is not None and payload.role != old_role:
            record_audit_event(session, action="USER_ROLE_CHANGED", resource_type="USER", resource_id=user.id, actor_id=current_user.id, ip_address=get_client_ip(request), request_id=get_request_id(request), details={"from": old_role, "to": payload.role})
        if payload.status is not None and payload.status != old_status:
            record_audit_event(session, action="USER_STATUS_CHANGED", resource_type="USER", resource_id=user.id, actor_id=current_user.id, ip_address=get_client_ip(request), request_id=get_request_id(request), details={"from": old_status, "to": payload.status})

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
    request: Request,
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
        record_audit_event(session, action="ADMIN_PASSWORD_RESET", resource_type="USER", resource_id=user.id, actor_id=current_user.id, ip_address=get_client_ip(request), request_id=get_request_id(request))
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


@router.get("/admin/audit-logs", status_code=status.HTTP_200_OK)
def admin_list_audit_logs(limit: int = 100, current_user: User = Depends(get_current_user)):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    with SessionLocal() as session:
        rows = session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()
        return [
            {
                "id": str(r.id),
                "actor_id": str(r.actor_id) if r.actor_id else None,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "details": r.details,
                "ip_address": r.ip_address,
                "request_id": r.request_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]


@router.post("/admin/approvals/role-change", status_code=status.HTTP_201_CREATED)
def request_role_change_approval(user_id: UUID, new_role: str, request: Request, current_user: User = Depends(get_current_user)):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    with SessionLocal() as session:
        if session.get(User, user_id) is None:
            raise HTTPException(status_code=404, detail="User not found")
        req = ApprovalRequest(action_type="ROLE_CHANGE", target_id=user_id, payload={"role": new_role}, requested_by=current_user.id)
        session.add(req)
        session.flush()
        record_audit_event(session, action="ROLE_CHANGE_REQUESTED", resource_type="USER", resource_id=user_id, actor_id=current_user.id, ip_address=get_client_ip(request), request_id=get_request_id(request), details={"approval_id": str(req.id), "role": new_role})
        session.commit()
        return {"id": str(req.id), "status": req.status, "action_type": req.action_type}


@router.post("/admin/approvals/{approval_id}/approve", status_code=status.HTTP_200_OK)
def approve_pending_request(approval_id: UUID, request: Request, current_user: User = Depends(get_current_user)):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    with SessionLocal() as session:
        req = session.get(ApprovalRequest, approval_id)
        if req is None:
            raise HTTPException(status_code=404, detail="Approval request not found")
        if req.status != "PENDING":
            raise HTTPException(status_code=409, detail="Approval request already resolved")
        if req.requested_by == current_user.id:
            raise HTTPException(status_code=409, detail="Four-eyes violation: requester cannot approve")
        if req.action_type == "ROLE_CHANGE":
            target = session.get(User, req.target_id)
            if target is None:
                raise HTTPException(status_code=404, detail="Target user not found")
            target.role = str(req.payload["role"])
            record_audit_event(session, action="ROLE_CHANGE_APPROVED", resource_type="USER", resource_id=target.id, actor_id=current_user.id, ip_address=get_client_ip(request), request_id=get_request_id(request), details={"approval_id": str(req.id), "role": target.role})
        req.status = "APPROVED"
        req.approved_by = current_user.id
        req.resolved_at = datetime.now(timezone.utc)
        session.commit()
        return {"id": str(req.id), "status": req.status, "approved_by": str(req.approved_by)}
