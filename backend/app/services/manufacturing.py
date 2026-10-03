"""Manufacturing security orchestration (Modules F/G/H/I/K). No HTTP here.

Ties the pure telemetry/anomaly/gcode modules to the database: creates PrintJob rows, records
SecurityEvents and Incidents on anomaly, "pauses" the simulator (a real state change, not a
cosmetic flag), and writes an audit trail for every step -- matching the spec's required chain:

    Telemetry -> Detection -> Security Event -> Incident -> Simulated Printer Pause -> Audit Log
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.hardware import get_hardware_profile
from app.manufacturing.anomaly import AnomalyResult
from app.manufacturing.gcode import analyze_gcode
from app.manufacturing.mes import get_mes_adapter
from app.manufacturing.simulator import RunningJob, registry
from app.manufacturing.telemetry import SCENARIOS
from app.ml.quality_model import ModelNotTrainedError
from app.ml.registry import get_process_model
from app.models import GCodeAnalysis, Incident, Printer, PrintJob, User
from app.services.security_events import record_security_event

_INCIDENT_TYPE_BY_METHOD = {"threshold": "PARAMETER_TAMPERING", "isolation_forest": "STATISTICAL_ANOMALY"}


def list_printers(db: Session) -> list[Printer]:
    return list(db.execute(select(Printer).order_by(Printer.id)).scalars())


def printer_out(printer: Printer) -> dict:
    job = registry.get(printer.id)
    return {
        "id": printer.id, "printer_code": printer.printer_code, "name": printer.name,
        "adapter": printer.adapter, "db_state": printer.state,
        "simulator_state": job.state if job else "IDLE",
        "scenario": job.scenario if job else None,
        "current_job_id": job.print_job_id if job else None,
    }


def _next_job_code(db: Session) -> str:
    count = db.execute(select(func.count()).select_from(PrintJob)).scalar_one()
    return f"JOB-{count + 1:06d}"


def _resolved_process_model():
    try:
        return get_process_model()
    except ModelNotTrainedError:
        return None  # anomaly detection still works via the threshold layer alone


async def start_print(db: Session, *, printer: Printer, scenario: str, actor: User,
                      seed: int | None = None) -> PrintJob:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    if registry.is_running(printer.id):
        raise RuntimeError(f"{printer.printer_code} already has a running print job")

    job = PrintJob(job_code=_next_job_code(db), printer_id=printer.id, scenario=scenario,
                   state="running", started_by=actor.id)
    db.add(job)
    printer.state = "printing"
    db.commit()
    db.refresh(job)

    get_mes_adapter().submit_job(job.id)
    tick_seconds = get_hardware_profile(get_settings().hardware_profile).simulator_tick_seconds
    process_model = _resolved_process_model()

    async def on_tick(running_job: RunningJob, sample: dict, result: AnomalyResult) -> None:
        from app.database import SessionLocal  # local import: avoids a import-time cycle
        with SessionLocal() as tick_db:
            if not result.anomaly:
                return
            handle_anomaly(tick_db, printer_id=printer.id, print_job_id=job.id,
                           sample=sample, result=result)
            running_job_row = tick_db.get(PrintJob, job.id)
            if running_job_row is not None:
                running_job_row.suspicious = True
                running_job_row.state = "paused"
                tick_db.commit()
            printer_row = tick_db.get(Printer, printer.id)
            if printer_row is not None:
                printer_row.state = "paused"
                tick_db.commit()
            registry.pause(printer.id)

    registry.start(printer.id, job.id, scenario, tick_seconds, seed, on_tick=on_tick,
                  process_model=process_model)
    return job


def handle_anomaly(db: Session, *, printer_id: int, print_job_id: int, sample: dict,
                   result: AnomalyResult) -> Incident:
    """The full required chain for one detected anomaly: security event, incident, audit."""
    printer = db.get(Printer, printer_id)
    resource = f"printer:{printer.printer_code}" if printer else f"printer:{printer_id}"
    reason = "; ".join(result.reasons) if result.reasons else "Anomaly detected"

    event = record_security_event(
        db, event_type=_INCIDENT_TYPE_BY_METHOD.get(result.method, "MANUFACTURING_ANOMALY"),
        severity=result.risk, source="printer-simulator", resource=resource, reason=reason,
        response="PRINT_PAUSED", details={"sample": sample, "method": result.method})

    incident = Incident(incident_type=event.event_type, severity=result.risk,
                        printer_id=printer_id, print_job_id=print_job_id,
                        action_taken="PRINT_PAUSED", status="OPEN",
                        description=f"{reason} (detected via {result.method})")
    db.add(incident)
    db.flush()
    incident.incident_code = f"INC-{incident.id:05d}"
    event.incident_id = incident.id
    db.commit()
    db.refresh(incident)
    return incident


def pause_printer(db: Session, printer: Printer) -> None:
    registry.pause(printer.id)
    printer.state = "paused"
    job = db.execute(select(PrintJob).where(
        PrintJob.printer_id == printer.id, PrintJob.state == "running"
    ).order_by(PrintJob.id.desc())).scalar_one_or_none()
    if job:
        job.state = "paused"
    db.commit()


def stop_printer(db: Session, printer: Printer) -> None:
    registry.stop(printer.id)
    printer.state = "idle"
    job = db.execute(select(PrintJob).where(
        PrintJob.printer_id == printer.id, PrintJob.state.in_(["running", "paused"])
    ).order_by(PrintJob.id.desc())).scalar_one_or_none()
    if job:
        job.state = "stopped"
    db.commit()


def get_telemetry(printer_id: int, limit: int = 30) -> list[dict]:
    return registry.latest_telemetry(printer_id, limit=limit)


def analyze_gcode_file(db: Session, *, filename: str, text: str, sha256: str,
                       user: User) -> GCodeAnalysis:
    # GCodeTooLargeError propagates unmodified to the caller (app/api/manufacturing.py), which
    # maps it to a 422 response -- no local handling is needed here.
    result = analyze_gcode(text)
    record = GCodeAnalysis(filename=filename, sha256=sha256, analyzed_by=user.id,
                           safe=result["safe"], risk=result["risk"],
                           findings=result["findings"], stats=result["stats"])
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def gcode_analysis_out(record: GCodeAnalysis) -> dict:
    return {"id": record.id, "filename": record.filename, "sha256": record.sha256,
           "safe": record.safe, "risk": record.risk, "findings": record.findings,
           "stats": record.stats, "created_at": record.created_at}


def list_incidents(db: Session, *, limit: int, offset: int) -> tuple[list[Incident], int]:
    total = db.execute(select(func.count()).select_from(Incident)).scalar_one()
    rows = db.execute(select(Incident).order_by(Incident.id.desc())
                      .limit(limit).offset(offset)).scalars().all()
    return rows, total


def incident_out(incident: Incident) -> dict:
    return {"id": incident.id, "incident_code": incident.incident_code,
           "incident_type": incident.incident_type, "severity": incident.severity,
           "printer_id": incident.printer_id, "print_job_id": incident.print_job_id,
           "action_taken": incident.action_taken, "status": incident.status,
           "description": incident.description, "opened_at": incident.opened_at,
           "resolved_at": incident.resolved_at}
