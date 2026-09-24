"""/api/audit: searchable audit log and hash-chain verification."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.audit.logger import verify_audit_chain, write_audit
from app.database import get_db
from app.models.security_events import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogOut, AuditLogPage, ChainVerificationOut
from app.security.rbac import Permission

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs", response_model=AuditLogPage)
def list_logs(
    user: str | None = Query(None, max_length=64),
    action: str | None = Query(None, max_length=64),
    resource: str | None = Query(None, max_length=255),
    result: str | None = Query(None, pattern="^(SUCCESS|FAILURE)$"),
    severity: str | None = Query(None, max_length=16),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = Query(None, max_length=100, description="free text over user/action/resource"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _viewer: User = Depends(require_permission(Permission.AUDIT_VIEW)),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog)
    if user:
        stmt = stmt.where(AuditLog.user == user)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource:
        stmt = stmt.where(AuditLog.resource.ilike(f"%{resource}%"))
    if result:
        stmt = stmt.where(AuditLog.result == result)
    if severity:
        stmt = stmt.where(AuditLog.severity == severity)
    if date_from:
        stmt = stmt.where(AuditLog.timestamp >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.timestamp <= date_to)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(AuditLog.user.ilike(like), AuditLog.action.ilike(like),
                              AuditLog.resource.ilike(like)))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).scalars().all()
    return AuditLogPage(total=total, limit=limit, offset=offset,
                        items=[AuditLogOut.model_validate(r) for r in rows])


@router.get("/verify", response_model=ChainVerificationOut)
def verify_chain_endpoint(
    request: Request,
    viewer: User = Depends(require_permission(Permission.AUDIT_VIEW)),
    db: Session = Depends(get_db),
):
    result = verify_audit_chain(db)
    write_audit(db, action="AUDIT_CHAIN_VERIFY", user=viewer.username, ip=client_ip(request),
                resource="audit_logs", result="SUCCESS" if result.valid else "FAILURE",
                severity="INFO" if result.valid else "HIGH",
                details={"checked": result.checked, "first_broken_id": result.first_broken_id})
    return ChainVerificationOut(valid=result.valid, checked=result.checked,
                                first_broken_id=result.first_broken_id, reason=result.reason)
