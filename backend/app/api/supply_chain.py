"""/api/supply-chain: parts, provenance events, chain verification, part authentication
(Modules D and E)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.audit.logger import write_audit
from app.blockchain.ledger import LedgerBackend, LocalHashChainLedger
from app.blockchain.workflow import WorkflowOrderError
from app.database import get_db
from app.models import Design, DesignVersion, Part, User
from app.schemas.supply_chain import (
    AuthenticateOut,
    ChainVerificationOut,
    EventCreate,
    EventOut,
    PartCreate,
    PartOut,
    ProvenanceOut,
)
from app.security.rbac import Permission
from app.services import supply_chain as svc
from app.services.keys import EncryptionNotConfigured, get_key_provider
from app.services.security_events import record_security_event

router = APIRouter(prefix="/api/supply-chain", tags=["supply-chain"])


def _ledger() -> LedgerBackend:
    try:
        return LocalHashChainLedger(get_key_provider())
    except EncryptionNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc


def _part_or_404(db: Session, part_id: int) -> Part:
    part = db.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    return part


@router.post("/parts", response_model=PartOut, status_code=201)
def create_part(
    body: PartCreate, request: Request,
    user: User = Depends(require_permission(Permission.PROVENANCE_CREATE)),
    db: Session = Depends(get_db),
):
    design = db.get(Design, body.design_id)
    if design is None:
        raise HTTPException(404, "Design not found")
    version = db.execute(select(DesignVersion).where(
        DesignVersion.design_id == design.id, DesignVersion.version == design.current_version
    )).scalar_one_or_none()
    if version is None:
        raise HTTPException(409, "Design has no current version to bind this part to")

    part = svc.create_part(db, design=design, version=version, batch=body.batch,
                           material=body.material, actor=user, ledger=_ledger(),
                           printer_id=body.printer_id)
    write_audit(db, action="PART_CREATE", user=user.username, ip=client_ip(request),
                resource=f"part:{part.part_code}",
                details={"design_code": design.design_code, "batch": body.batch})
    return PartOut(**svc.part_out(db, part))


@router.get("/parts", response_model=list[PartOut])
def list_parts(_user: User = Depends(require_permission(Permission.PROVENANCE_VERIFY)),
              db: Session = Depends(get_db)):
    parts = db.execute(select(Part).order_by(Part.id.desc())).scalars().all()
    return [PartOut(**svc.part_out(db, p)) for p in parts]


@router.get("/parts/{part_id}", response_model=ProvenanceOut)
def get_part(part_id: int, _user: User = Depends(require_permission(Permission.PROVENANCE_VERIFY)),
            db: Session = Depends(get_db)):
    part = _part_or_404(db, part_id)
    return ProvenanceOut(**svc.part_provenance(db, part, _ledger()))


@router.post("/parts/{part_id}/events", response_model=EventOut, status_code=201)
def add_event(
    part_id: int, body: EventCreate, request: Request,
    user: User = Depends(require_permission(Permission.PROVENANCE_CREATE)),
    db: Session = Depends(get_db),
):
    part = _part_or_404(db, part_id)
    try:
        row = svc.append_event(db, part=part, actor=user, action=body.action, ledger=_ledger(),
                               status=body.status, payload=body.payload)
    except WorkflowOrderError as exc:
        write_audit(db, action="PROVENANCE_EVENT_REJECTED", user=user.username,
                    ip=client_ip(request), resource=f"part:{part.part_code}", result="FAILURE",
                    severity="WARNING", details={"requested_action": body.action, "reason": str(exc)})
        raise HTTPException(409, str(exc)) from exc
    write_audit(db, action="PROVENANCE_EVENT_CREATE", user=user.username, ip=client_ip(request),
                resource=f"part:{part.part_code}",
                details={"action": body.action, "event_id": row.event_id})
    return EventOut(**svc.event_out(row))


@router.get("/parts/{part_id}/verify", response_model=ChainVerificationOut)
def verify_part(part_id: int, request: Request,
                user: User = Depends(require_permission(Permission.PROVENANCE_VERIFY)),
                db: Session = Depends(get_db)):
    part = _part_or_404(db, part_id)
    result = svc.verify_part_chain(db, part, _ledger())
    write_audit(db, action="PROVENANCE_CHAIN_VERIFY", user=user.username, ip=client_ip(request),
                resource=f"part:{part.part_code}", result="SUCCESS" if result.valid else "FAILURE",
                severity="INFO" if result.valid else "HIGH",
                details={"checked": result.checked, "first_broken_id": result.first_broken_id})
    if not result.valid:
        record_security_event(
            db, event_type="PROVENANCE_TAMPER_DETECTED", severity="HIGH",
            source="supply-chain-verification", resource=f"part:{part.part_code}",
            reason=f"Provenance chain integrity failure at event #{result.first_broken_id}: "
                   f"{result.reason}",
            response="LOGGED", details={"checked": result.checked})
    return ChainVerificationOut(valid=result.valid, checked=result.checked,
                                first_broken_event=result.first_broken_id, reason=result.reason)


@router.get("/authenticate/{part_code}", response_model=AuthenticateOut)
def authenticate(part_code: str, request: Request,
                 user: User = Depends(require_permission(Permission.PART_AUTHENTICATE)),
                 db: Session = Depends(get_db)):
    result = svc.authenticate_part(db, part_code, _ledger())
    ok = result["verdict"] == "AUTHENTIC"
    write_audit(db, action="PART_AUTHENTICATE", user=user.username, ip=client_ip(request),
                resource=f"part:{part_code}", result="SUCCESS" if ok else "FAILURE",
                severity="INFO" if ok else ("HIGH" if result["verdict"] == "TAMPERED" else "WARNING"),
                details={"verdict": result["verdict"]})
    if result["verdict"] == "TAMPERED":
        record_security_event(
            db, event_type="PART_AUTHENTICATION_TAMPERED", severity="HIGH",
            source="part-authentication", resource=f"part:{part_code}",
            reason=result["reason"], response="LOGGED")
    return AuthenticateOut(**result)
