"""/api/dashboard: aggregate counts for the dashboard, straight from the database."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.database import get_db
from app.models import (
    AuditLog,
    ComplianceControl,
    Design,
    Incident,
    Part,
    PrintJob,
    QualityInspection,
    SupplyChainEvent,
    User,
)
from app.schemas.dashboard import ComplianceCounts, DashboardSummary
from app.security.rbac import Permission

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _count(db: Session, model, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    for condition in conditions:
        stmt = stmt.where(condition)
    return db.execute(stmt).scalar_one()


@router.get("/summary", response_model=DashboardSummary)
def summary(
    _user: User = Depends(require_permission(Permission.DASHBOARD_VIEW)),
    db: Session = Depends(get_db),
):
    by_status = dict(
        db.execute(
            select(ComplianceControl.status, func.count()).group_by(ComplianceControl.status)
        ).all()
    )
    return DashboardSummary(
        designs=_count(db, Design),
        active_prints=_count(db, PrintJob, PrintJob.state.in_(["running", "paused"])),
        defects_detected=_count(db, QualityInspection,
                                QualityInspection.status == "defect_detected"),
        incidents_open=_count(db, Incident, Incident.status == "OPEN"),
        incidents_total=_count(db, Incident),
        parts=_count(db, Part),
        supply_chain_events=_count(db, SupplyChainEvent),
        audit_events=_count(db, AuditLog),
        compliance=ComplianceCounts(
            pass_count=by_status.get("PASS", 0),
            fail_count=by_status.get("FAIL", 0),
            unknown_count=by_status.get("UNKNOWN", 0),
            total=sum(by_status.values()),
        ),
    )
