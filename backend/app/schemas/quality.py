from datetime import datetime

from pydantic import BaseModel, Field


class InspectionOut(BaseModel):
    inspection_id: int | None = None
    id: int | None = None
    status: str
    defect_type: str
    confidence: float
    severity: str
    class_probabilities: dict[str, float]
    model_version: str
    created_at: datetime
    cv_report: dict | None = None
    image_sha256: str | None = None


class InspectionListItem(BaseModel):
    id: int
    status: str
    defect_type: str
    confidence: float
    severity: str
    model_version: str
    created_at: datetime
    image_sha256: str
    class_probabilities: dict[str, float]


class InspectionPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[InspectionListItem]


class ProcessParametersIn(BaseModel):
    nozzle_temp_c: float = Field(ge=0, le=500)
    bed_temp_c: float = Field(ge=0, le=300)
    speed_mm_s: float = Field(ge=0, le=1000)
    layer_height_mm: float = Field(ge=0.01, le=2.0)
    extrusion_rate_pct: float = Field(ge=0, le=500)
    duration_min: float = Field(ge=0, le=100_000)


class OutOfRangeParam(BaseModel):
    value: float
    safe_range: list[float]


class ProcessPredictionOut(BaseModel):
    predicted_quality: str
    quality_probabilities: dict[str, float]
    anomaly_score: float
    is_anomaly: bool
    risk_level: str
    model_version: str
    out_of_range_parameters: dict[str, OutOfRangeParam]


class ModelMetricsOut(BaseModel):
    model_name: str
    trained_at: datetime
    dataset_description: str
    n_train: int
    n_validation: int
    metrics: dict
    disclaimer: str
