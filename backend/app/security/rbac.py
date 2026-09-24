"""Role-based access control: pure data, no framework imports (unit-testable).

Enforcement lives in app/api/deps.py (require_permission). Ownership rules
("engineers see only their own designs") are enforced in the service layer from Phase 4.
Production: roles/permissions come from enterprise IAM claims instead of this table.
"""
from enum import Enum


class RoleName(str, Enum):
    ADMIN = "ADMIN"
    ENGINEER = "ENGINEER"
    QUALITY_INSPECTOR = "QUALITY_INSPECTOR"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    AUDITOR = "AUDITOR"
    VIEWER = "VIEWER"


class Permission(str, Enum):
    DASHBOARD_VIEW = "dashboard:view"
    DESIGN_UPLOAD = "design:upload"
    DESIGN_VIEW = "design:view"            # own designs for ENGINEER; all for ADMIN
    DESIGN_DOWNLOAD = "design:download"    # own designs for ENGINEER; all for ADMIN
    DESIGN_VERIFY = "design:verify"
    QUALITY_INSPECT = "quality:inspect"
    QUALITY_VIEW = "quality:view"
    PROVENANCE_CREATE = "provenance:create"
    PROVENANCE_VERIFY = "provenance:verify"
    PART_AUTHENTICATE = "part:authenticate"
    PRINTER_CONTROL = "printer:control"
    GCODE_ANALYZE = "gcode:analyze"
    INCIDENT_VIEW = "incident:view"
    AUDIT_VIEW = "audit:view"
    COMPLIANCE_VIEW = "compliance:view"
    USER_MANAGE = "user:manage"


P = Permission

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    RoleName.ADMIN.value: frozenset(Permission),
    RoleName.ENGINEER.value: frozenset({
        P.DASHBOARD_VIEW, P.DESIGN_UPLOAD, P.DESIGN_VIEW, P.DESIGN_DOWNLOAD, P.DESIGN_VERIFY,
        P.QUALITY_VIEW, P.PROVENANCE_CREATE, P.PROVENANCE_VERIFY, P.PART_AUTHENTICATE,
        P.PRINTER_CONTROL, P.GCODE_ANALYZE, P.INCIDENT_VIEW,
    }),
    RoleName.QUALITY_INSPECTOR.value: frozenset({
        P.DASHBOARD_VIEW, P.DESIGN_VERIFY, P.QUALITY_INSPECT, P.QUALITY_VIEW,
        P.PROVENANCE_CREATE, P.PROVENANCE_VERIFY, P.PART_AUTHENTICATE, P.INCIDENT_VIEW,
    }),
    RoleName.SUPPLY_CHAIN.value: frozenset({
        P.DASHBOARD_VIEW, P.DESIGN_VERIFY, P.QUALITY_VIEW, P.PROVENANCE_CREATE,
        P.PROVENANCE_VERIFY, P.PART_AUTHENTICATE,
    }),
    RoleName.AUDITOR.value: frozenset({
        P.DASHBOARD_VIEW, P.DESIGN_VERIFY, P.QUALITY_VIEW, P.PROVENANCE_VERIFY,
        P.PART_AUTHENTICATE, P.INCIDENT_VIEW, P.AUDIT_VIEW, P.COMPLIANCE_VIEW,
    }),
    RoleName.VIEWER.value: frozenset({
        P.DASHBOARD_VIEW, P.PROVENANCE_VERIFY, P.PART_AUTHENTICATE, P.INCIDENT_VIEW,
    }),
}

ROLE_DESCRIPTIONS = {
    "ADMIN": "Full access, including user and role management",
    "ENGINEER": "Uploads and manages own designs, controls printers, analyses G-code",
    "QUALITY_INSPECTOR": "Runs quality inspections and reviews quality reports",
    "SUPPLY_CHAIN": "Records provenance events and authenticates parts",
    "AUDITOR": "Read-only access to audit logs, compliance evidence and provenance verification",
    "VIEWER": "Read-only: part authentication, provenance verification, incidents",
}


def has_permission(role_name: str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role_name, frozenset())
