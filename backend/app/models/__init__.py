"""Import every model so Base.metadata knows all tables."""
from app.models.compliance import ComplianceControl, MLModelMetrics
from app.models.design import Design, Design4DProfile, DesignFingerprint, DesignVersion
from app.models.manufacturing import GCodeAnalysis, Printer, PrintJob
from app.models.quality import Defect, QualityInspection
from app.models.security_events import AuditLog, Incident, SecurityEvent
from app.models.supply_chain import Part, SupplyChainEvent
from app.models.user import RevokedToken, Role, User

__all__ = [
    "AuditLog", "ComplianceControl", "Defect", "Design", "Design4DProfile", "DesignFingerprint",
    "DesignVersion", "GCodeAnalysis", "Incident", "MLModelMetrics", "Part", "PrintJob", "Printer",
    "QualityInspection", "RevokedToken", "Role", "SecurityEvent", "SupplyChainEvent", "User",
]
