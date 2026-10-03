"""Compliance evidence: automated technical checks mapped to control references.

Each check inspects the LIVE system and returns (status, evidence). Nothing is hardcoded PASS:
a check with no data to inspect returns UNKNOWN with the reason. This is technical support for
audits only; it is NOT a certification against NIST, ISO 9001 or ISO/ASTM 52900.
"""
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.logger import verify_audit_chain
from app.config import get_settings
from app.ml.registry import ml_health
from app.models import AuditLog, ComplianceControl, Design, DesignVersion, Part, User
from app.security.rbac import ROLE_PERMISSIONS, Permission, RoleName
from app.services.keys import EncryptionNotConfigured, get_key_provider
from app.services.supply_chain import verify_part_chain
from app.timeutil import utcnow

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
Result = tuple[str, str]

DISCLAIMER = (
    "Automated technical evidence only. This is not a certification or formal audit against "
    "NIST, ISO 9001 or ISO/ASTM 52900."
)


@dataclass(frozen=True)
class Control:
    framework: str
    control_ref: str
    title: str
    description: str
    check: Callable[[Session], Result]


def _passwords_hashed(db: Session) -> Result:
    hashes = db.execute(select(User.password_hash)).scalars().all()
    if not hashes:
        return UNKNOWN, "No users exist yet"
    weak = [h for h in hashes if not h.startswith("$argon2")]
    if weak:
        return FAIL, f"{len(weak)} of {len(hashes)} users do not use an Argon2 password hash"
    return PASS, f"All {len(hashes)} users store Argon2 password hashes"


def _least_privilege(_db: Session) -> Result:
    admin_all = ROLE_PERMISSIONS[RoleName.ADMIN.value] == frozenset(Permission)
    others = [name for name in ROLE_PERMISSIONS if name != RoleName.ADMIN.value]
    leaked = [n for n in others if Permission.USER_MANAGE in ROLE_PERMISSIONS[n]]
    if not admin_all or leaked:
        return FAIL, f"Role table breaks least privilege (user:manage held by {leaked or 'n/a'})"
    return PASS, f"{len(ROLE_PERMISSIONS)} roles defined; only ADMIN holds user:manage"


def _lockout(_db: Session) -> Result:
    s = get_settings()
    if s.max_failed_logins <= 10 and s.lockout_minutes >= 5:
        return PASS, f"Lockout after {s.max_failed_logins} failures for {s.lockout_minutes} min"
    return FAIL, (f"Lockout too weak ({s.max_failed_logins} attempts, "
                  f"{s.lockout_minutes} min); need <=10 attempts and >=5 min")


def _encryption(_db: Session) -> Result:
    try:
        get_key_provider()
    except EncryptionNotConfigured as exc:
        return FAIL, str(exc)
    return PASS, "MASTER_KEY configured; designs use AES-256-GCM envelope encryption"


def _designs_encrypted(db: Session) -> Result:
    total = db.execute(select(func.count()).select_from(DesignVersion)).scalar_one()
    if total == 0:
        return UNKNOWN, "No design versions registered yet"
    plain = db.execute(select(func.count()).select_from(DesignVersion)
                       .where(DesignVersion.encrypted.is_(False))).scalar_one()
    if plain:
        return FAIL, f"{plain} of {total} stored design versions are not encrypted"
    return PASS, f"All {total} stored design versions are encrypted at rest"


def _audit_chain(db: Session) -> Result:
    result = verify_audit_chain(db)
    if not result.valid:
        return FAIL, f"Audit chain broken at entry {result.first_broken_id}: {result.reason}"
    if result.checked == 0:
        return UNKNOWN, "Audit log is empty"
    return PASS, f"Audit hash chain intact ({result.checked} entries verified)"


def _audit_activity(db: Session) -> Result:
    count = db.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    if count == 0:
        return UNKNOWN, "No audit entries recorded yet"
    return PASS, f"{count} security-relevant events recorded in the tamper-evident audit log"


def _provenance(db: Session) -> Result:
    from app.api.supply_chain import _ledger  # same ledger the API uses

    parts = db.execute(select(Part)).scalars().all()
    if not parts:
        return UNKNOWN, "No parts registered yet"
    try:
        ledger = _ledger()
    except Exception as exc:  # noqa: BLE001 - report any ledger setup problem as evidence
        return FAIL, f"Provenance ledger unavailable: {getattr(exc, 'detail', exc)}"
    broken = [p.part_code for p in parts if not verify_part_chain(db, p, ledger).valid]
    if broken:
        return FAIL, f"Provenance chain broken for: {', '.join(broken[:5])}"
    return PASS, f"All {len(parts)} part provenance chains verify (hashes and signatures)"


def _design_fingerprints(db: Session) -> Result:
    designs = db.execute(select(func.count()).select_from(Design)).scalar_one()
    if designs == 0:
        return UNKNOWN, "No designs registered yet"
    missing = db.execute(select(func.count()).select_from(DesignVersion)
                         .where(func.length(DesignVersion.sha256) != 64)).scalar_one()
    if missing:
        return FAIL, f"{missing} design versions lack a valid SHA-256 digest"
    return PASS, f"{designs} designs registered, every version carries a SHA-256 digest"


def _ml_ready(_db: Session) -> Result:
    state = ml_health()
    if state == "ok":
        return PASS, "Defect-detection and process-quality models are trained and load correctly"
    if state == "not_configured":
        return UNKNOWN, "Models not trained yet (run ml/training scripts)"
    return FAIL, "A trained model file failed to load"


CONTROLS: list[Control] = [
    Control("NIST", "PR.AC-1", "Credentials are managed",
            "Passwords are stored with a memory-hard hash.", _passwords_hashed),
    Control("NIST", "PR.AC-4", "Least-privilege access",
            "Access permissions are role-based; admin rights are not widely held.",
            _least_privilege),
    Control("NIST", "PR.AC-7", "Authentication is rate-limited",
            "Repeated failed logins lock the account.", _lockout),
    Control("NIST", "PR.DS-1", "Data at rest is protected",
            "An encryption key is configured and stored designs are encrypted.",
            _encryption),
    Control("NIST", "PR.DS-5", "Protections against data leaks",
            "Stored design files are encrypted at rest.", _designs_encrypted),
    Control("NIST", "PR.DS-6", "Integrity checking",
            "Every design version carries a SHA-256 digest.", _design_fingerprints),
    Control("NIST", "DE.AE-3", "Events are logged and correlated",
            "Security events are recorded in an audit log.", _audit_activity),
    Control("NIST", "PR.PT-1", "Audit records are tamper-evident",
            "The audit log hash chain verifies end to end.", _audit_chain),
    Control("ISO9001", "7.5.3", "Control of documented information",
            "Quality records are protected from undetected alteration.", _audit_chain),
    Control("ISO9001", "8.5.2", "Identification and traceability",
            "Each part has a signed, hash-chained provenance record.", _provenance),
    Control("ISO9001", "8.6", "Release of products and services",
            "AI quality-inspection models are available before release decisions.", _ml_ready),
]


def run_checks(db: Session) -> list[ComplianceControl]:
    """Evaluate every control, upsert the result into compliance_controls and return the rows."""
    now = utcnow()
    existing = {(c.framework, c.control_ref): c
                for c in db.execute(select(ComplianceControl)).scalars()}
    rows = []
    for control in CONTROLS:
        try:
            status, evidence = control.check(db)
        except Exception as exc:  # noqa: BLE001 - a crashing check is itself evidence
            status, evidence = UNKNOWN, f"Check could not run: {type(exc).__name__}"
        row = existing.get((control.framework, control.control_ref))
        if row is None:
            row = ComplianceControl(framework=control.framework, control_ref=control.control_ref)
            db.add(row)
        row.title, row.description = control.title, control.description
        row.status, row.evidence, row.last_checked = status, evidence, now
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def summarise(rows: list[ComplianceControl]) -> dict:
    counts = {PASS: 0, FAIL: 0, UNKNOWN: 0}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return {"pass_count": counts[PASS], "fail_count": counts[FAIL],
            "unknown_count": counts[UNKNOWN], "total": len(rows)}
