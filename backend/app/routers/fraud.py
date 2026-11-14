import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from app.db.models import (
    Account,
    FraudAlert,
    FraudAlertStatus,
    OutboxEvent,
    ProcessedEvent,
    User,
)
from app.db.session import SessionLocal
from app.schemas.fraud import FraudAlertResponse, FraudResolutionRequest
from app.schemas.risk import RiskAssessmentRequest
from app.security.dependencies import get_current_user
from app.security.permissions import Permission, has_permission
from app.security.tokens import (
    revoke_all_user_sessions,
)
from app.services.risk_assessment import assess_transaction_risk

logger = logging.getLogger("finguard.security")

router = APIRouter()



@router.get("/fraud/alerts", response_model=list[FraudAlertResponse])
def list_fraud_alerts(
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.FRAUD_ALERT_READ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as db:
        query = select(FraudAlert)
        if status_filter:
            query = query.where(FraudAlert.status == status_filter.upper())
        alerts = db.scalars(query.order_by(FraudAlert.created_at.desc())).all()
        return [
            FraudAlertResponse(
                id=a.id,
                transaction_id=a.transaction_id,
                account_id=a.account_id,
                risk_score=float(a.risk_score) / 1000.0,
                reasons=a.reasons,
                status=a.status.value if hasattr(a.status, 'value') else str(a.status),
                analyst_id=a.analyst_id,
                analyst_notes=a.analyst_notes,
                created_at=a.created_at,
                resolved_at=a.resolved_at,
            )
            for a in alerts
        ]


@router.post("/fraud/alerts/{alert_id}/investigate", response_model=FraudAlertResponse)
def start_investigation(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.FRAUD_ALERT_RESOLVE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as db:
        alert = db.get(FraudAlert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Fraud alert not found")

        current_status = alert.status.value if hasattr(alert.status, "value") else str(alert.status)
        if current_status != FraudAlertStatus.PENDING.value:
            raise HTTPException(
                status_code=409,
                detail=f"Invalid alert state transition from {current_status} to INVESTIGATING",
            )
        alert.status = FraudAlertStatus.INVESTIGATING
        alert.analyst_id = current_user.id
        db.commit()
        db.refresh(alert)
        return FraudAlertResponse(
            id=alert.id,
            transaction_id=alert.transaction_id,
            account_id=alert.account_id,
            risk_score=float(alert.risk_score) / 1000.0,
            reasons=alert.reasons,
            status=alert.status if isinstance(alert.status, str) else alert.status.value,
            analyst_id=alert.analyst_id,
            analyst_notes=alert.analyst_notes,
            created_at=alert.created_at,
            resolved_at=alert.resolved_at,
        )


@router.post("/fraud/alerts/{alert_id}/resolve", response_model=FraudAlertResponse)
def resolve_alert(
    alert_id: UUID,
    payload: FraudResolutionRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.FRAUD_ALERT_RESOLVE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as db:
        alert = db.get(FraudAlert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Fraud alert not found")

        current_status = alert.status.value if hasattr(alert.status, "value") else str(alert.status)
        if current_status not in (FraudAlertStatus.PENDING.value, FraudAlertStatus.INVESTIGATING.value):
            raise HTTPException(
                status_code=409,
                detail=f"Invalid alert state transition from {current_status} to {payload.decision}",
            )
        alert.status = FraudAlertStatus(payload.decision)
        alert.analyst_id = current_user.id
        alert.analyst_notes = payload.analyst_notes
        alert.resolved_at = datetime.now(timezone.utc)

        if payload.decision == FraudAlertStatus.BLOCKED.value:
            flagged_account = db.get(Account, alert.account_id)
            if flagged_account is not None and flagged_account.user_id is not None:
                owner = db.get(User, flagged_account.user_id)
                if owner is not None:
                    owner.status = "SUSPENDED"
                    revoke_all_user_sessions(db, owner.id)

        db.commit()
        db.refresh(alert)
        return FraudAlertResponse(
            id=alert.id,
            transaction_id=alert.transaction_id,
            account_id=alert.account_id,
            risk_score=float(alert.risk_score) / 1000.0,
            reasons=alert.reasons,
            status=alert.status if isinstance(alert.status, str) else alert.status.value,
            analyst_id=alert.analyst_id,
            analyst_notes=alert.analyst_notes,
            created_at=alert.created_at,
            resolved_at=alert.resolved_at,
        )


@router.post("/risk/assess")
def assess_risk_endpoint(
    data: RiskAssessmentRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(
        current_user.role, Permission.RISK_ASSESS
    ):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions"
        )
    result = assess_transaction_risk(
        amount_cents=data.amount_cents,
        transfers_last_10min=data.transfers_last_10min,
        account_age_minutes=data.account_age_minutes,
        failed_transfers_last_hour=data.failed_transfers_last_hour,
    )

    return result


@router.get("/monitoring/events")
def get_event_monitoring(
    current_user: User = Depends(get_current_user),
):
    if not has_permission(
        current_user.role, Permission.MONITORING_READ
    ):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions"
        )
    with SessionLocal() as db:

        # =============================================
        # 1. EVENT STATISTICS
        # =============================================
        total_events = db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
        ) or 0

        pending_events = db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
        ) or 0

        published_events = db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.published_at.is_not(None))
        ) or 0

        processed_events = db.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
        ) or 0

        # =============================================
        # 2. RECENT EVENTS WITH CONSUMER STATUS (LEFT JOIN)
        # =============================================
        recent_rows = db.execute(
            select(OutboxEvent, ProcessedEvent.processed_at)
            .outerjoin(
                ProcessedEvent,
                OutboxEvent.id == ProcessedEvent.event_id,
            )
            .order_by(OutboxEvent.created_at.desc())
            .limit(10)
        ).all()

        recent_events = []
        for event, processed_at in recent_rows:
            if processed_at is not None:
                status = "PROCESSED"
            elif event.published_at is not None:
                status = "PUBLISHED"
            else:
                status = "PENDING"

            recent_events.append({
                "event_id": str(event.id),
                "event_type": event.event_type,
                "aggregate_id": str(event.aggregate_id),
                "created_at": event.created_at.isoformat(),
                "published_at": (
                    event.published_at.isoformat()
                    if event.published_at
                    else None
                ),
                "processed_at": (
                    processed_at.isoformat()
                    if processed_at
                    else None
                ),
                "publish_attempts": event.publish_attempts,
                "status": status,
            })

    return {
        "total_events": total_events,
        "pending_events": pending_events,
        "published_events": published_events,
        "processed_events": processed_events,
        "recent_events": recent_events,
    }
