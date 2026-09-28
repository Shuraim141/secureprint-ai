"""Quality-control orchestration: image inspection and process-parameter prediction.
No HTTP here; app/api/quality.py wraps these for FastAPI."""
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cv.inspection import inspect as run_cv_inspection
from app.ml.process_dataset import FEATURE_NAMES as PROCESS_FEATURE_NAMES
from app.ml.process_dataset import SAFE_RANGES, to_feature_vector
from app.ml.quality_features import extract_features
from app.ml.registry import get_defect_detector, get_process_model
from app.models import Defect, MLModelMetrics, QualityInspection, User


def inspect_image(db: Session, *, gray, image_bytes: bytes, target_size: int,
                  inspector: User, part_id: int | None, print_job_id: int | None) -> dict:
    detector = get_defect_detector()  # raises ModelNotTrainedError -> caller maps to 503
    cv_report = run_cv_inspection(gray, target_size)
    prediction = detector.predict(extract_features(gray, target_size))

    status = "normal" if prediction.predicted_class == "NORMAL" else "defect_detected"
    record = QualityInspection(
        part_id=part_id, print_job_id=print_job_id, inspector_id=inspector.id,
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
        predicted_class=prediction.predicted_class, status=status,
        confidence=prediction.confidence, severity=prediction.severity,
        model_version=detector.model_version,
        details={"class_probabilities": prediction.class_probabilities,
                 "cv_report": {k: v for k, v in cv_report.items() if not k.endswith("_base64")}},
    )
    db.add(record)
    db.flush()
    if status == "defect_detected":
        db.add(Defect(inspection_id=record.id, defect_type=prediction.predicted_class,
                      confidence=prediction.confidence, severity=prediction.severity))
    db.commit()
    db.refresh(record)

    return {
        "inspection_id": record.id, "status": status, "defect_type": prediction.predicted_class,
        "confidence": prediction.confidence, "severity": prediction.severity,
        "class_probabilities": prediction.class_probabilities, "model_version": detector.model_version,
        "created_at": record.created_at, "cv_report": cv_report,
    }


def inspection_out(record: QualityInspection) -> dict:
    return {
        "id": record.id, "status": record.status, "defect_type": record.predicted_class,
        "confidence": record.confidence, "severity": record.severity,
        "model_version": record.model_version, "created_at": record.created_at,
        "image_sha256": record.image_sha256,
        "class_probabilities": (record.details or {}).get("class_probabilities", {}),
    }


def list_inspections(db: Session, *, limit: int, offset: int) -> tuple[list[QualityInspection], int]:
    from sqlalchemy import func
    total = db.execute(select(func.count()).select_from(QualityInspection)).scalar_one()
    rows = db.execute(select(QualityInspection).order_by(QualityInspection.id.desc())
                      .limit(limit).offset(offset)).scalars().all()
    return rows, total


def predict_process_quality(values: dict) -> dict:
    model = get_process_model()  # raises ModelNotTrainedError -> caller maps to 503
    prediction = model.predict(to_feature_vector(values))
    out_of_range = {
        name: {"value": values[name], "safe_range": list(SAFE_RANGES[name])}
        for name in PROCESS_FEATURE_NAMES
        if not (SAFE_RANGES[name][0] <= values[name] <= SAFE_RANGES[name][1])
    }
    return {
        "predicted_quality": prediction.predicted_quality,
        "quality_probabilities": prediction.quality_probabilities,
        "anomaly_score": prediction.anomaly_score, "is_anomaly": prediction.is_anomaly,
        "risk_level": prediction.risk_level, "model_version": model.model_version,
        "out_of_range_parameters": out_of_range,
    }


def latest_model_metrics(db: Session, model_name: str) -> MLModelMetrics | None:
    return db.execute(
        select(MLModelMetrics).where(MLModelMetrics.model_name == model_name)
        .order_by(MLModelMetrics.trained_at.desc()).limit(1)
    ).scalar_one_or_none()
