"""/api/manufacturing: printer simulator control, telemetry, G-code analysis, incidents
(Modules F, G, H, I, K)."""
import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.audit.logger import write_audit
from app.config import get_settings
from app.database import get_db
from app.manufacturing.gcode import GCodeTooLargeError
from app.models import Printer, User
from app.schemas.manufacturing import (
    GCodeAnalysisOut,
    IncidentOut,
    IncidentPage,
    PrinterOut,
    StartPrintIn,
    TelemetryOut,
)
from app.security.rbac import Permission
from app.security.uploads import UploadTooLarge, read_limited
from app.services import manufacturing as svc

router = APIRouter(prefix="/api/manufacturing", tags=["manufacturing"])
MAX_GCODE_BYTES = 2 * 1024 * 1024  # 2 MB is generous for a demo file


def _printer_or_404(db: Session, printer_id: int) -> Printer:
    printer = db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(404, "Printer not found")
    return printer


@router.get("/printers", response_model=list[PrinterOut])
def list_printers(_user: User = Depends(require_permission(Permission.PRINTER_CONTROL,
                                                           Permission.DASHBOARD_VIEW)),
                  db: Session = Depends(get_db)):
    return [svc.printer_out(p) for p in svc.list_printers(db)]


@router.post("/printers/{printer_id}/start", response_model=PrinterOut, status_code=201)
async def start_print(printer_id: int, body: StartPrintIn, request: Request,
                      user: User = Depends(require_permission(Permission.PRINTER_CONTROL)),
                      db: Session = Depends(get_db)):
    printer = _printer_or_404(db, printer_id)
    try:
        await svc.start_print(db, printer=printer, scenario=body.scenario, actor=user,
                              seed=body.seed)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    write_audit(db, action="PRINTER_START", user=user.username, ip=client_ip(request),
                resource=f"printer:{printer.printer_code}",
                details={"scenario": body.scenario, "seed": body.seed})
    return svc.printer_out(printer)


@router.post("/printers/{printer_id}/pause", response_model=PrinterOut)
def pause_print(printer_id: int, request: Request,
                user: User = Depends(require_permission(Permission.PRINTER_CONTROL)),
                db: Session = Depends(get_db)):
    printer = _printer_or_404(db, printer_id)
    svc.pause_printer(db, printer)
    write_audit(db, action="PRINTER_PAUSE", user=user.username, ip=client_ip(request),
                resource=f"printer:{printer.printer_code}")
    return svc.printer_out(printer)


@router.post("/printers/{printer_id}/stop", response_model=PrinterOut)
def stop_print(printer_id: int, request: Request,
               user: User = Depends(require_permission(Permission.PRINTER_CONTROL)),
               db: Session = Depends(get_db)):
    printer = _printer_or_404(db, printer_id)
    svc.stop_printer(db, printer)
    write_audit(db, action="PRINTER_STOP", user=user.username, ip=client_ip(request),
                resource=f"printer:{printer.printer_code}")
    return svc.printer_out(printer)


@router.get("/printers/{printer_id}/telemetry", response_model=TelemetryOut)
def get_telemetry(printer_id: int, limit: int = Query(30, ge=1, le=120),
                  _user: User = Depends(require_permission(Permission.PRINTER_CONTROL,
                                                           Permission.DASHBOARD_VIEW)),
                  db: Session = Depends(get_db)):
    printer = _printer_or_404(db, printer_id)
    samples = svc.get_telemetry(printer_id, limit=limit)
    from app.manufacturing.simulator import registry
    job = registry.get(printer_id)
    return TelemetryOut(printer_id=printer_id, simulator_state=job.state if job else "IDLE",
                        samples=samples)


@router.post("/analyze-gcode", response_model=GCodeAnalysisOut)
def analyze_gcode_endpoint(
    request: Request, file: UploadFile = File(...),
    user: User = Depends(require_permission(Permission.GCODE_ANALYZE)),
    db: Session = Depends(get_db),
):
    try:
        data = read_limited(file.file, min(MAX_GCODE_BYTES, get_settings().max_upload_bytes))
    except UploadTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "File is not valid UTF-8 text") from exc
    try:
        record = svc.analyze_gcode_file(db, filename=file.filename or "upload.gcode", text=text,
                                        sha256=hashlib.sha256(data).hexdigest(), user=user)
    except GCodeTooLargeError as exc:
        raise HTTPException(422, str(exc)) from exc

    write_audit(db, action="GCODE_ANALYZE", user=user.username, ip=client_ip(request),
                resource=f"gcode:{record.id}", result="SUCCESS" if record.safe else "FAILURE",
                severity="INFO" if record.safe else ("HIGH" if record.risk == "HIGH" else "WARNING"),
                details={"filename": record.filename, "risk": record.risk})
    if record.risk == "HIGH":
        from app.services.security_events import record_security_event
        record_security_event(
            db, event_type="MALICIOUS_GCODE_DETECTED", severity="HIGH", source="gcode-analyzer",
            resource=f"gcode:{record.id}",
            reason=f"{record.filename}: " + "; ".join(f["message"] for f in record.findings[:3]),
            response="LOGGED")
    return GCodeAnalysisOut(**svc.gcode_analysis_out(record))


@router.get("/incidents", response_model=IncidentPage)
def list_incidents(limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0),
                   _user: User = Depends(require_permission(Permission.INCIDENT_VIEW)),
                   db: Session = Depends(get_db)):
    rows, total = svc.list_incidents(db, limit=limit, offset=offset)
    return IncidentPage(total=total, limit=limit, offset=offset,
                        items=[IncidentOut(**svc.incident_out(r)) for r in rows])
