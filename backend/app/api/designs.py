"""/api/designs: 3D/4D design registration, analysis, encrypted storage, verification."""
import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.audit.logger import write_audit
from app.config import get_settings
from app.database import get_db
from app.geometry.parsers import GeometryError, UnsupportedFormatError
from app.models import Design, DesignVersion, User
from app.schemas.designs import (
    DesignDetailOut,
    DesignSummaryOut,
    FourDProfileIn,
    FourDProfileOut,
    FourDVerifyOut,
    VerifyOut,
)
from app.security.crypto import KeyProvider
from app.security.rbac import Permission
from app.security.uploads import UploadTooLarge, read_limited, sanitize_display_name
from app.services import designs as svc
from app.services.keys import EncryptionNotConfigured, get_key_provider
from app.services.security_events import record_security_event
from app.storage import LocalFileStorage

router = APIRouter(prefix="/api/designs", tags=["designs"])


# ------------------------------------------------------------------ helpers
def _provider() -> KeyProvider:
    try:
        return get_key_provider()
    except EncryptionNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc


def _storage() -> LocalFileStorage:
    return LocalFileStorage(get_settings().storage_dir / "designs")


def _reject(db: Session, user: User, request: Request, status: int, message: str, action: str):
    write_audit(db, action="DESIGN_UPLOAD_REJECTED", user=user.username, ip=client_ip(request),
                resource=request.url.path, result="FAILURE", severity="WARNING",
                details={"status": status, "reason": message, "operation": action})
    return HTTPException(status, message)


def _read_and_parse(file: UploadFile, db: Session, user: User, request: Request, operation: str):
    try:
        data = read_limited(file.file, get_settings().max_upload_bytes)
    except UploadTooLarge as exc:
        raise _reject(db, user, request, 413, str(exc), operation) from exc
    try:
        return svc.parse_model(file.filename, data)
    except UnsupportedFormatError as exc:
        raise _reject(db, user, request, 415, str(exc), operation) from exc
    except GeometryError as exc:
        raise _reject(db, user, request, 422, str(exc), operation) from exc


def _owned_design(db: Session, design_id: int, user: User, request: Request) -> Design:
    design = db.get(Design, design_id)
    if design is None:
        raise HTTPException(404, "Design not found")
    if user.role.name != "ADMIN" and design.owner_id != user.id:
        write_audit(db, action="DESIGN_ACCESS_DENIED", user=user.username, ip=client_ip(request),
                    resource=f"design:{design.design_code}", result="FAILURE", severity="WARNING",
                    details={"reason": "not the owner"})
        raise HTTPException(404, "Design not found")  # 404: do not confirm it exists
    return design


def _version_or_404(db: Session, design: Design, version: int) -> DesignVersion:
    row = svc._version_row(db, design.id, version)
    if row is None:
        raise HTTPException(404, "Version not found")
    return row


def _audit_registration(db: Session, user: User, request: Request, design: Design,
                        version: DesignVersion, action: str) -> None:
    ip, resource = client_ip(request), f"design:{design.design_code}"
    write_audit(db, action=action, user=user.username, ip=ip, resource=resource, details={
        "version": version.version, "sha256": version.sha256,
        "format": (version.analysis or {}).get("format"),
        "triangles": (version.analysis or {}).get("triangle_count")})
    write_audit(db, action="DESIGN_ENCRYPT", user=user.username, ip=ip, resource=resource,
                details={"algorithm": version.encryption_alg, "version": version.version})


def _integrity_failure(db: Session, user: User, request: Request, design: Design,
                       version: int, message: str) -> HTTPException:
    resource = f"design:{design.design_code}"
    record_security_event(
        db, event_type="STORAGE_INTEGRITY_FAILURE", severity="HIGH", source="design-storage",
        resource=resource, reason=message, response="ACCESS_BLOCKED",
        details={"version": version, "user": user.username})
    write_audit(db, action="DESIGN_INTEGRITY_FAILURE", user=user.username, ip=client_ip(request),
                resource=resource, result="FAILURE", severity="HIGH",
                details={"version": version, "reason": message})
    return HTTPException(409, f"Stored design failed its integrity check: {message}")


def _attachment(data: bytes, filename: str) -> Response:
    safe = sanitize_display_name(filename, "design.stl")  # ASCII subset: safe inside a header
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})


# ------------------------------------------------------------------ verification (first: static path)
@router.post("/verify", response_model=VerifyOut)
def verify_design(
    request: Request,
    file: UploadFile = File(...),
    design_id: int | None = Form(None),
    user: User = Depends(require_permission(Permission.DESIGN_VERIFY)),
    db: Session = Depends(get_db),
):
    """Check an uploaded file against the registry (SHA-256, geometric fingerprint, watermark)."""
    provider = _provider()
    try:
        data = read_limited(file.file, get_settings().max_upload_bytes)
    except UploadTooLarge as exc:
        raise _reject(db, user, request, 413, str(exc), "verify") from exc
    design = None
    if design_id is not None:
        design = db.get(Design, design_id)
        if design is None:
            raise HTTPException(404, "Design not found")
    try:
        result = svc.verify_upload(db, filename=file.filename, data=data, design=design,
                                   provider=provider, viewer=user)
    except UnsupportedFormatError as exc:
        raise _reject(db, user, request, 415, str(exc), "verify") from exc

    verdict, matched = result["verdict"], result["matched_design"]
    resource = f"design:{matched['design_code']}" if matched else "design-registry"
    ok = verdict in {"AUTHENTIC", "GEOMETRY_MATCH"}
    severity = "INFO" if ok else ("HIGH" if verdict == "TAMPERED" else "WARNING")
    write_audit(db, action="DESIGN_VERIFY", user=user.username, ip=client_ip(request),
                resource=resource, result="SUCCESS" if ok else "FAILURE", severity=severity,
                details={"verdict": verdict, "sha256": result["sha256"], "match_type": result["match_type"]})
    if verdict == "TAMPERED":
        record_security_event(
            db, event_type="DESIGN_TAMPER_DETECTED", severity="HIGH", source="design-verification",
            resource=resource, reason=result["headline"], response="LOGGED",
            details={"sha256": result["sha256"], "verified_by": user.username})
    return VerifyOut(**result)


# ------------------------------------------------------------------ registration and listing
@router.post("", response_model=DesignDetailOut, status_code=201)
def register_design(
    request: Request,
    file: UploadFile = File(...),
    name: str | None = Form(None, max_length=200),
    user: User = Depends(require_permission(Permission.DESIGN_UPLOAD)),
    db: Session = Depends(get_db),
):
    """Validate, analyse, fingerprint, watermark and encrypt a 3D model, then register it."""
    provider = _provider()
    parsed = _read_and_parse(file, db, user, request, "register")
    try:
        design, version, warnings = svc.register_design(
            db, user=user, parsed=parsed, name=name, storage=_storage(), provider=provider)
    except svc.DuplicateDesignError as exc:
        write_audit(db, action="DESIGN_REGISTER_DUPLICATE", user=user.username,
                    ip=client_ip(request), resource=f"design:{exc.design_code}", result="FAILURE",
                    severity="WARNING", details={"sha256": parsed.sha256})
        raise HTTPException(409, f"This exact file is already registered as {exc.design_code}") from exc
    _audit_registration(db, user, request, design, version, "DESIGN_REGISTER")
    return svc.design_detail(db, design, warnings)


@router.get("", response_model=list[DesignSummaryOut])
def list_designs(user: User = Depends(require_permission(Permission.DESIGN_VIEW)),
                 db: Session = Depends(get_db)):
    stmt = select(Design).order_by(Design.id.desc())
    if user.role.name != "ADMIN":
        stmt = stmt.where(Design.owner_id == user.id)
    return svc.design_summaries(db, list(db.execute(stmt).scalars()))


@router.get("/{design_id}", response_model=DesignDetailOut)
def get_design(design_id: int, request: Request,
               user: User = Depends(require_permission(Permission.DESIGN_VIEW)),
               db: Session = Depends(get_db)):
    return svc.design_detail(db, _owned_design(db, design_id, user, request))


@router.post("/{design_id}/versions", response_model=DesignDetailOut, status_code=201)
def add_design_version(
    design_id: int, request: Request, file: UploadFile = File(...),
    user: User = Depends(require_permission(Permission.DESIGN_UPLOAD)),
    db: Session = Depends(get_db),
):
    provider = _provider()
    design = _owned_design(db, design_id, user, request)
    parsed = _read_and_parse(file, db, user, request, "new-version")
    try:
        design, version, warnings = svc.add_version(
            db, user=user, design=design, parsed=parsed, storage=_storage(), provider=provider)
    except svc.DuplicateDesignError as exc:
        raise HTTPException(409, f"This exact file is already registered as {exc.design_code}") from exc
    _audit_registration(db, user, request, design, version, "DESIGN_VERSION_ADD")
    return svc.design_detail(db, design, warnings)


# ------------------------------------------------------------------ downloads
@router.get("/{design_id}/versions/{version}/download")
def download_version(design_id: int, version: int, request: Request,
                     user: User = Depends(require_permission(Permission.DESIGN_DOWNLOAD)),
                     db: Session = Depends(get_db)):
    """Decrypt the stored original and return it. Verifies GCM tag and SHA-256 first."""
    provider = _provider()
    design = _owned_design(db, design_id, user, request)
    row = _version_or_404(db, design, version)
    try:
        plaintext = svc.read_version_plaintext(row, _storage(), provider)
    except svc.IntegrityFailure as exc:
        raise _integrity_failure(db, user, request, design, version, str(exc)) from exc
    write_audit(db, action="DESIGN_DOWNLOAD", user=user.username, ip=client_ip(request),
                resource=f"design:{design.design_code}",
                details={"version": version, "sha256": row.sha256, "decrypted": True})
    return _attachment(plaintext, row.original_filename)


@router.get("/{design_id}/versions/{version}/watermarked")
def download_watermarked(design_id: int, version: int, request: Request,
                         user: User = Depends(require_permission(Permission.DESIGN_DOWNLOAD)),
                         db: Session = Depends(get_db)):
    """Generate the watermarked distribution copy (binary STL) from the decrypted original."""
    provider = _provider()
    design = _owned_design(db, design_id, user, request)
    row = _version_or_404(db, design, version)
    try:
        copy = svc.build_watermarked_copy(db, design, row, _storage(), provider)
    except svc.WatermarkUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc
    except svc.IntegrityFailure as exc:
        raise _integrity_failure(db, user, request, design, version, str(exc)) from exc
    write_audit(db, action="DESIGN_WATERMARK_ISSUE", user=user.username, ip=client_ip(request),
                resource=f"design:{design.design_code}",
                details={"version": version, "distribution_sha256": hashlib.sha256(copy).hexdigest()})
    stem = row.original_filename.rsplit(".", 1)[0]
    return _attachment(copy, f"{stem}_watermarked.stl")


# ------------------------------------------------------------------ 4D metadata
@router.put("/{design_id}/4d", response_model=FourDProfileOut)
def put_4d_profile(design_id: int, body: FourDProfileIn, request: Request,
                   user: User = Depends(require_permission(Permission.DESIGN_UPLOAD)),
                   db: Session = Depends(get_db)):
    design = _owned_design(db, design_id, user, request)
    profile = svc.set_4d_profile(db, design=design, user=user, values=body.model_dump())
    write_audit(db, action="DESIGN_4D_PROFILE_SET", user=user.username, ip=client_ip(request),
                resource=f"design:{design.design_code}",
                details={"trigger_type": body.trigger_type, "material_id": body.material_id,
                         "security_fingerprint": profile.security_fingerprint})
    return svc.profile_out(db, profile)


@router.get("/{design_id}/4d", response_model=FourDProfileOut)
def get_4d_profile(design_id: int, request: Request,
                   user: User = Depends(require_permission(Permission.DESIGN_VIEW)),
                   db: Session = Depends(get_db)):
    design = _owned_design(db, design_id, user, request)
    if design.profile_4d is None:
        raise HTTPException(404, "This design has no 4D profile")
    return svc.profile_out(db, design.profile_4d)


@router.post("/{design_id}/4d/verify", response_model=FourDVerifyOut)
def verify_4d_profile(design_id: int, request: Request,
                      user: User = Depends(require_permission(Permission.DESIGN_VIEW)),
                      db: Session = Depends(get_db)):
    design = _owned_design(db, design_id, user, request)
    if design.profile_4d is None:
        raise HTTPException(404, "This design has no 4D profile")
    result = svc.verify_4d_profile(db, design, design.profile_4d)
    resource = f"design:{design.design_code}"
    write_audit(db, action="DESIGN_4D_VERIFY", user=user.username, ip=client_ip(request),
                resource=resource, result="SUCCESS" if result["intact"] else "FAILURE",
                severity="INFO" if result["intact"] else "HIGH", details={"intact": result["intact"]})
    if not result["intact"]:
        record_security_event(
            db, event_type="4D_PROFILE_TAMPER_DETECTED", severity="HIGH", source="design-4d",
            resource=resource, reason=result["reason"], response="LOGGED")
    return FourDVerifyOut(**result)
