"""/api/quality: AI defect detection (image), predictive quality analytics (process params)."""
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.audit.logger import write_audit
from app.config import get_settings
from app.cv.inspection import ImageValidationError, decode_image
from app.database import get_db
from app.hardware import get_hardware_profile
from app.ml.quality_model import ModelNotTrainedError
from app.models import QualityInspection, User
from app.schemas.quality import (
    InspectionOut,
    InspectionPage,
    ModelMetricsOut,
    ProcessParametersIn,
    ProcessPredictionOut,
)
from app.security.rbac import Permission
from app.security.uploads import UploadTooLarge, read_limited
from app.services import quality as svc
from app.services.security_events import record_security_event

router = APIRouter(prefix="/api/quality", tags=["quality"])

_MODEL_UNAVAILABLE = (
    "The defect-detection model is not trained yet. Run "
    "'python ml/training/train_defect_model.py' (see ml/README.md), then try again."
)
_PROCESS_MODEL_UNAVAILABLE = (
    "The process-quality model is not trained yet. Run "
    "'python ml/training/train_process_model.py' (see ml/README.md), then try again."
)


@router.post("/inspect", response_model=InspectionOut)
def inspect(
    request: Request,
    file: UploadFile = File(...),
    part_id: int | None = None,
    print_job_id: int | None = None,
    user: User = Depends(require_permission(Permission.QUALITY_INSPECT)),
    db: Session = Depends(get_db),
):
    """Upload a print/manufacturing image and run AI defect detection on it."""
    settings = get_settings()
    try:
        data = read_limited(file.file, settings.max_upload_bytes)
    except UploadTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    try:
        gray = decode_image(data)
    except ImageValidationError as exc:
        write_audit(db, action="QUALITY_INSPECT_REJECTED", user=user.username, ip=client_ip(request),
                    result="FAILURE", severity="WARNING", details={"reason": str(exc)})
        raise HTTPException(422, str(exc)) from exc

    target_size = get_hardware_profile(settings.hardware_profile).ml_image_size
    try:
        result = svc.inspect_image(db, gray=gray, image_bytes=data, target_size=target_size,
                                   inspector=user, part_id=part_id, print_job_id=print_job_id)
    except ModelNotTrainedError as exc:
        raise HTTPException(503, _MODEL_UNAVAILABLE) from exc

    severity_level = {"none": "INFO", "low": "INFO", "medium": "WARNING", "high": "HIGH"}
    write_audit(db, action="QUALITY_INSPECT", user=user.username, ip=client_ip(request),
                resource=f"inspection:{result['inspection_id']}",
                severity=severity_level.get(result["severity"], "INFO"),
                details={"defect_type": result["defect_type"], "confidence": result["confidence"],
                         "severity": result["severity"]})
    if result["severity"] == "high":
        record_security_event(
            db, event_type="HIGH_SEVERITY_DEFECT", severity="HIGH", source="quality-inspection",
            resource=f"inspection:{result['inspection_id']}",
            reason=f"AI quality inspection detected {result['defect_type']} "
                   f"(confidence {result['confidence']})", response="LOGGED")
    return InspectionOut(**result)


@router.get("/history", response_model=InspectionPage)
def history(
    limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0),
    _user: User = Depends(require_permission(Permission.QUALITY_VIEW)),
    db: Session = Depends(get_db),
):
    rows, total = svc.list_inspections(db, limit=limit, offset=offset)
    return InspectionPage(total=total, limit=limit, offset=offset,
                          items=[svc.inspection_out(r) for r in rows])


@router.get("/history/{inspection_id}", response_model=InspectionOut)
def get_inspection(inspection_id: int,
                   _user: User = Depends(require_permission(Permission.QUALITY_VIEW)),
                   db: Session = Depends(get_db)):
    record = db.get(QualityInspection, inspection_id)
    if record is None:
        raise HTTPException(404, "Inspection not found")
    return InspectionOut(**svc.inspection_out(record))


@router.post("/predict", response_model=ProcessPredictionOut)
def predict(
    body: ProcessParametersIn, request: Request,
    user: User = Depends(require_permission(Permission.QUALITY_VIEW)),
    db: Session = Depends(get_db),
):
    """Predictive quality analytics from print process parameters (Module A3)."""
    try:
        result = svc.predict_process_quality(body.model_dump())
    except ModelNotTrainedError as exc:
        raise HTTPException(503, _PROCESS_MODEL_UNAVAILABLE) from exc
    write_audit(db, action="QUALITY_PREDICT", user=user.username, ip=client_ip(request),
                details={"predicted_quality": result["predicted_quality"],
                         "risk_level": result["risk_level"], "is_anomaly": result["is_anomaly"]})
    if result["risk_level"] == "HIGH":
        record_security_event(
            db, event_type="PROCESS_QUALITY_RISK", severity="MEDIUM", source="quality-predict",
            resource=None, reason=(
                f"Predictive quality analytics rated print parameters HIGH risk "
                f"(predicted {result['predicted_quality']}, anomaly_score "
                f"{result['anomaly_score']})"),
            response="LOGGED", details={"parameters": body.model_dump()})
    return ProcessPredictionOut(**result)


@router.get("/models/{model_name}", response_model=ModelMetricsOut)
def model_metrics(model_name: str,
                  _user: User = Depends(require_permission(Permission.QUALITY_VIEW)),
                  db: Session = Depends(get_db)):
    if model_name not in {"defect_detector", "process_quality"}:
        raise HTTPException(404, "Unknown model name")
    record = svc.latest_model_metrics(db, model_name)
    if record is None:
        raise HTTPException(404, f"No training run recorded for '{model_name}' yet. "
                                 "Run the matching script under ml/training/.")
    return ModelMetricsOut(model_name=record.model_name, trained_at=record.trained_at,
                           dataset_description=record.dataset_description,
                           n_train=record.n_train, n_validation=record.n_validation,
                           metrics=record.metrics, disclaimer=record.disclaimer)
