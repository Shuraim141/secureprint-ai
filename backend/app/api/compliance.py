"""/api/compliance: automated technical evidence mapped to control references."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.audit.logger import write_audit
from app.database import get_db
from app.models import ComplianceControl
from app.models.user import User
from app.schemas.compliance import ComplianceReport, ControlOut
from app.security.rbac import Permission
from app.services import compliance as svc
from app.timeutil import utcnow

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


def _report(rows: list[ComplianceControl]) -> ComplianceReport:
    return ComplianceReport(generated_at=utcnow(), disclaimer=svc.DISCLAIMER,
                            controls=[ControlOut.model_validate(r) for r in rows],
                            **svc.summarise(rows))


@router.get("/controls", response_model=ComplianceReport)
def list_controls(
    _user: User = Depends(require_permission(Permission.COMPLIANCE_VIEW)),
    db: Session = Depends(get_db),
):
    """Last stored results (no re-check). Controls never evaluated show UNKNOWN."""
    rows = list(db.execute(select(ComplianceControl).order_by(
        ComplianceControl.framework, ComplianceControl.control_ref)).scalars())
    return _report(rows)


@router.post("/run", response_model=ComplianceReport)
def run_checks(
    request: Request,
    user: User = Depends(require_permission(Permission.COMPLIANCE_VIEW)),
    db: Session = Depends(get_db),
):
    """Re-evaluate every control against the live system and store the evidence."""
    rows = svc.run_checks(db)
    summary = svc.summarise(rows)
    write_audit(db, action="COMPLIANCE_RUN", user=user.username, ip=client_ip(request),
                resource="compliance", result="FAILURE" if summary["fail_count"] else "SUCCESS",
                severity="WARNING" if summary["fail_count"] else "INFO", details=summary)
    return _report(rows)
