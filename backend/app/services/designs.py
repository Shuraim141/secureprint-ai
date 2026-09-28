"""Design registration, verification and 4D profiles (business logic, no HTTP)."""
import base64
import hashlib
import json
import uuid
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.chain import canonical_json
from app.config import get_settings
from app.geometry.analysis import GEOMETRY_QUANTUM_MM, analyze_mesh, geometric_fingerprint
from app.geometry.parsers import (
    GeometryError,
    MeshLimits,
    UnsupportedFormatError,
    detect_format,
    parse_mesh,
)
from app.geometry.watermark import WatermarkCapacityError, detect, embed
from app.geometry.writers import write_binary_stl
from app.hardware import get_hardware_profile
from app.models import Design, Design4DProfile, DesignFingerprint, DesignVersion, User
from app.security.crypto import ALGORITHM, CryptoError, KeyProvider, decrypt_bytes, encrypt_bytes
from app.security.uploads import sanitize_display_name
from app.storage import StorageBackend

DIST_HEADER = b"SecurePrint AI watermarked distribution copy"
_TRIANGLE_LIMITS = {"low": 200_000, "standard": 500_000, "high": 1_000_000}
FOURD_FIELDS = ("material_id", "material_name", "material_class", "trigger_type",
                "trigger_temperature_c", "trigger_time_s", "target_state",
                "transformation_profile", "activation_conditions")


class DuplicateDesignError(Exception):
    def __init__(self, design_code: str, registered_at):
        super().__init__(design_code)
        self.design_code, self.registered_at = design_code, registered_at


class IntegrityFailure(Exception):
    """A stored design file failed its cryptographic integrity check."""


class WatermarkUnavailable(Exception):
    pass


def get_mesh_limits() -> MeshLimits:
    profile = get_hardware_profile(get_settings().hardware_profile)
    return MeshLimits(max_triangles=_TRIANGLE_LIMITS[profile.name])


@dataclass
class ParsedModel:
    display_name: str
    fmt: str
    data: bytes
    sha256: str
    triangles: np.ndarray
    analysis: dict
    geometric_fp: str


def parse_model(filename: str | None, data: bytes) -> ParsedModel:
    """Validate and analyse an uploaded model. Raises GeometryError / UnsupportedFormatError."""
    fmt = detect_format(filename or "", data)
    triangles = parse_mesh(data, fmt, get_mesh_limits())
    return ParsedModel(
        display_name=sanitize_display_name(filename), fmt=fmt, data=data,
        sha256=hashlib.sha256(data).hexdigest(), triangles=triangles,
        analysis={**analyze_mesh(triangles), "format": fmt},
        geometric_fp=geometric_fingerprint(triangles),
    )


# ---------------------------------------------------------------- lookups
def _hits(db: Session, kind: str, value: str, limit: int = 5):
    stmt = (
        select(DesignFingerprint, DesignVersion, Design)
        .join(DesignVersion, DesignVersion.id == DesignFingerprint.design_version_id)
        .join(Design, Design.id == DesignVersion.design_id)
        .where(DesignFingerprint.kind == kind, DesignFingerprint.value == value)
        .order_by(DesignFingerprint.id).limit(limit)
    )
    return db.execute(stmt).all()


def _version_row(db: Session, design_id: int, version: int) -> DesignVersion | None:
    return db.execute(select(DesignVersion).where(
        DesignVersion.design_id == design_id, DesignVersion.version == version)).scalar_one_or_none()


def _fingerprint(db: Session, version_id: int, kind: str) -> DesignFingerprint | None:
    return db.execute(select(DesignFingerprint).where(
        DesignFingerprint.design_version_id == version_id,
        DesignFingerprint.kind == kind)).scalar_one_or_none()


def _watermark_key(provider: KeyProvider, design_code: str, version: int) -> bytes:
    return provider.derive_subkey(f"watermark:{design_code}:v{version}")


# ---------------------------------------------------------------- registration
def _watermark_record(parsed: ParsedModel, design_code: str, version: int,
                      provider: KeyProvider) -> tuple[str, dict]:
    try:
        marked, info = embed(parsed.triangles, _watermark_key(provider, design_code, version))
    except WatermarkCapacityError as exc:
        return "not_applied", {"status": "not_applied", "reason": str(exc)}
    distribution = write_binary_stl(marked, header=DIST_HEADER)
    digest = hashlib.sha256(distribution).hexdigest()
    return digest, {
        "status": "applied", **info, "distribution_sha256": digest,
        "distribution_format": "binary STL",
        "note": "Fragile keyed watermark (prototype). Survives lossless copies and small local "
                "edits; destroyed by re-ordering, rounding, scaling or re-meshing.",
    }


def _store_version(db: Session, *, design: Design, parsed: ParsedModel, user: User,
                   storage: StorageBackend, provider: KeyProvider, version: int,
                   storage_key: str) -> DesignVersion:
    blob = encrypt_bytes(parsed.data, aad=storage_key.encode("ascii"), key_provider=provider)
    storage.save(storage_key, blob.ciphertext)
    row = DesignVersion(
        design_id=design.id, version=version, original_filename=parsed.display_name,
        storage_key=storage_key, file_size=len(parsed.data), sha256=parsed.sha256,
        encrypted=True, encryption_alg=ALGORITHM,
        nonce_b64=base64.b64encode(blob.nonce).decode(),
        wrapped_key_b64=base64.b64encode(blob.wrapped_key).decode(),
        analysis=parsed.analysis, created_by=user.id,
    )
    db.add(row)
    db.flush()
    wm_value, wm_meta = _watermark_record(parsed, design.design_code, version, provider)
    db.add_all([
        DesignFingerprint(design_version_id=row.id, kind="sha256", value=parsed.sha256,
                          meta={"algorithm": "SHA-256"}),
        DesignFingerprint(design_version_id=row.id, kind="geometric", value=parsed.geometric_fp,
                          meta={"algorithm": "SPGF1", "quantum_mm": GEOMETRY_QUANTUM_MM}),
        DesignFingerprint(design_version_id=row.id, kind="watermark", value=wm_value, meta=wm_meta),
    ])
    return row


def _check_duplicate(db: Session, parsed: ParsedModel) -> list[str]:
    exact = _hits(db, "sha256", parsed.sha256, 1)
    if exact:
        _, version, design = exact[0]
        raise DuplicateDesignError(design.design_code, version.created_at)
    return [f"Geometry is identical to registered design {d.design_code}"
            for _, _, d in _hits(db, "geometric", parsed.geometric_fp, 1)]


def register_design(db: Session, *, user: User, parsed: ParsedModel, name: str | None,
                    storage: StorageBackend, provider: KeyProvider):
    warnings = _check_duplicate(db, parsed)
    storage_key = uuid.uuid4().hex + ".enc"
    title = sanitize_display_name(name) if name else parsed.display_name.rsplit(".", 1)[0]
    design = Design(name=title, owner_id=user.id, file_format=parsed.fmt, current_version=1)
    try:
        db.add(design)
        db.flush()
        design.design_code = f"SP-3D-{design.id:06d}"
        version = _store_version(db, design=design, parsed=parsed, user=user, storage=storage,
                                 provider=provider, version=1, storage_key=storage_key)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(storage_key)
        raise
    return design, version, warnings


def add_version(db: Session, *, user: User, design: Design, parsed: ParsedModel,
                storage: StorageBackend, provider: KeyProvider):
    warnings = _check_duplicate(db, parsed)
    latest = db.execute(select(DesignVersion.version).where(DesignVersion.design_id == design.id)
                        .order_by(DesignVersion.version.desc()).limit(1)).scalar_one()
    storage_key = uuid.uuid4().hex + ".enc"
    try:
        version = _store_version(db, design=design, parsed=parsed, user=user, storage=storage,
                                 provider=provider, version=latest + 1, storage_key=storage_key)
        design.current_version = latest + 1
        design.file_format = parsed.fmt
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(storage_key)
        raise
    return design, version, warnings


# ---------------------------------------------------------------- read models
def _usernames(db: Session, ids: set[int]) -> dict[int, str]:
    rows = db.execute(select(User.id, User.username).where(User.id.in_(ids))).all()
    return {i: name for i, name in rows}


def design_summaries(db: Session, designs: list[Design]) -> list[dict]:
    if not designs:
        return []
    names = _usernames(db, {d.owner_id for d in designs})
    out = []
    for d in designs:
        current = _version_row(db, d.id, d.current_version)
        out.append({
            "id": d.id, "design_code": d.design_code, "name": d.name,
            "owner": names.get(d.owner_id, "unknown"), "file_format": d.file_format,
            "current_version": d.current_version, "is_4d": d.is_4d, "created_at": d.created_at,
            "sha256": current.sha256 if current else "",
            "triangle_count": (current.analysis or {}).get("triangle_count") if current else None,
            "encrypted": bool(current and current.encrypted),
        })
    return out


def profile_out(db: Session, profile: Design4DProfile) -> dict:
    names = _usernames(db, {profile.created_by})
    return {**{f: getattr(profile, f) for f in FOURD_FIELDS},
            "security_fingerprint": profile.security_fingerprint,
            "design_version": profile.design_version,
            "created_by": names.get(profile.created_by, "unknown"),
            "created_at": profile.created_at}


def design_detail(db: Session, design: Design, warnings: list[str] | None = None) -> dict:
    versions = db.execute(select(DesignVersion).where(DesignVersion.design_id == design.id)
                          .order_by(DesignVersion.version)).scalars().all()
    profile = db.execute(select(Design4DProfile).where(
        Design4DProfile.design_id == design.id)).scalar_one_or_none()
    ids = {design.owner_id, *[v.created_by for v in versions]}
    if profile:
        ids.add(profile.created_by)
    names = _usernames(db, ids)
    version_out, history = [], []
    for v in versions:
        fps = db.execute(select(DesignFingerprint).where(
            DesignFingerprint.design_version_id == v.id)
            .order_by(DesignFingerprint.id)).scalars().all()
        actor = names.get(v.created_by, "unknown")
        version_out.append({
            "version": v.version, "original_filename": v.original_filename,
            "file_size": v.file_size, "sha256": v.sha256, "encrypted": v.encrypted,
            "encryption_alg": v.encryption_alg, "created_by": actor, "created_at": v.created_at,
            "analysis": v.analysis,
            "fingerprints": [{"kind": f.kind, "value": f.value, "meta": f.meta} for f in fps],
        })
        history.append({"time": v.created_at, "actor": actor,
                        "event": "DESIGN_REGISTERED" if v.version == 1 else "VERSION_ADDED",
                        "detail": f"v{v.version} · SHA-256 {v.sha256[:16]}…"})
    if profile:
        history.append({"time": profile.created_at, "actor": names.get(profile.created_by, "unknown"),
                        "event": "4D_PROFILE_SET",
                        "detail": f"{profile.material_name} · trigger {profile.trigger_type}"})
    history.sort(key=lambda e: e["time"])
    summary = design_summaries(db, [design])[0]
    return {**summary, "versions": version_out, "history": history, "warnings": warnings or [],
            "profile_4d": profile_out(db, profile) if profile else None}


# ---------------------------------------------------------------- decryption
def read_version_plaintext(row: DesignVersion, storage: StorageBackend,
                           provider: KeyProvider) -> bytes:
    try:
        ciphertext = storage.load(row.storage_key)
    except (FileNotFoundError, ValueError) as exc:
        raise IntegrityFailure("Encrypted file is missing from storage") from exc
    try:
        plaintext = decrypt_bytes(
            ciphertext, nonce=base64.b64decode(row.nonce_b64),
            wrapped_key=base64.b64decode(row.wrapped_key_b64),
            aad=row.storage_key.encode("ascii"), key_provider=provider)
    except CryptoError as exc:
        raise IntegrityFailure(str(exc)) from exc
    if hashlib.sha256(plaintext).hexdigest() != row.sha256:
        raise IntegrityFailure("Decrypted file does not match its registered SHA-256")
    return plaintext


def build_watermarked_copy(db: Session, design: Design, row: DesignVersion,
                           storage: StorageBackend, provider: KeyProvider) -> bytes:
    mark = _fingerprint(db, row.id, "watermark")
    if mark is None or (mark.meta or {}).get("status") != "applied":
        reason = (mark.meta or {}).get("reason", "no watermark record") if mark else "no record"
        raise WatermarkUnavailable(f"No watermarked copy exists for this version: {reason}")
    plaintext = read_version_plaintext(row, storage, provider)
    fmt = (row.analysis or {}).get("format", design.file_format)
    triangles = parse_mesh(plaintext, fmt, get_mesh_limits())
    marked, _ = embed(triangles, _watermark_key(provider, design.design_code, row.version))
    copy = write_binary_stl(marked, header=DIST_HEADER)
    if hashlib.sha256(copy).hexdigest() != mark.meta["distribution_sha256"]:
        raise IntegrityFailure("Regenerated watermarked copy does not match its recorded hash")
    return copy


# ---------------------------------------------------------------- verification
_METRICS = ("triangle_count", "vertex_count", "volume_mm3", "surface_area_mm2")


def compare_analysis(registered: dict, uploaded: dict) -> dict:
    flat_r = {**registered, **{f"dimension_{k}_mm": v for k, v in registered["dimensions_mm"].items()}}
    flat_u = {**uploaded, **{f"dimension_{k}_mm": v for k, v in uploaded["dimensions_mm"].items()}}
    metrics, changed = {}, []
    for name in (*_METRICS, "dimension_x_mm", "dimension_y_mm", "dimension_z_mm"):
        r, u = flat_r[name], flat_u[name]
        differs = abs(u - r) > 1e-6 * max(1.0, abs(r))
        metrics[name] = {"registered": r, "uploaded": u, "delta": round(u - r, 6),
                         "delta_pct": round(100 * (u - r) / r, 4) if r else None,
                         "changed": bool(differs)}
        if differs:
            changed.append(name)
    return {"metrics": metrics, "changed": changed}


def verify_upload(db: Session, *, filename: str | None, data: bytes, design: Design | None,
                  provider: KeyProvider, viewer: User) -> dict:
    """Decide whether an uploaded file matches what was registered. Raises
    UnsupportedFormatError for disallowed extensions; every other outcome is a verdict."""
    sha = hashlib.sha256(data).hexdigest()
    is_admin = viewer.role.name == "ADMIN"
    result: dict = {
        "filename": sanitize_display_name(filename), "sha256": sha, "verdict": "UNREGISTERED",
        "headline": "", "reasons": [], "match_type": None, "matched_design": None,
        "checks": {"sha256_match": False, "geometric_match": False, "watermark": None},
        "differences": None, "uploaded_analysis": None, "uploaded_geometric_fingerprint": None,
    }

    def ref(d: Design, version: int) -> dict:
        return {"design_id": d.id, "design_code": d.design_code, "name": d.name, "version": version}

    for kind, match_type, label in (
        ("sha256", "original", "Byte-for-byte identical to the registered file"),
        ("watermark", "watermarked_copy",
         "Byte-for-byte identical to the watermarked distribution copy issued for this design"),
    ):
        hits = _hits(db, kind, sha, 1)
        if hits:
            _, ver, found = hits[0]
            result.update(match_type=match_type, matched_design=ref(found, ver.version))
            result["checks"]["sha256_match"] = True
            if design is not None and found.id != design.id:
                result.update(verdict="WRONG_DESIGN", headline=(
                    f"File is registered, but as {found.design_code} and not {design.design_code}"))
            else:
                result.update(verdict="AUTHENTIC", headline=f"AUTHENTIC: {label}",
                              reasons=[f"SHA-256 matches {found.design_code} v{ver.version}"])
            return result

    try:
        fmt = detect_format(filename or "", data)
        triangles = parse_mesh(data, fmt, get_mesh_limits())
    except UnsupportedFormatError:
        raise
    except GeometryError as exc:
        result.update(verdict="INVALID_FILE", headline="File is not a valid 3D model",
                      reasons=[str(exc), "It matches no registered file byte-for-byte"])
        return result

    geo = geometric_fingerprint(triangles)
    analysis = {**analyze_mesh(triangles), "format": fmt}
    result.update(uploaded_analysis=analysis, uploaded_geometric_fingerprint=geo)

    geo_hits = _hits(db, "geometric", geo, 5)
    if design is not None:
        geo_hits = [h for h in geo_hits if h[2].id == design.id] or geo_hits[:1]
    if geo_hits:
        _, ver, found = geo_hits[0]
        result.update(match_type="geometry", matched_design=ref(found, ver.version))
        result["checks"]["geometric_match"] = True
        if design is not None and found.id != design.id:
            result.update(verdict="WRONG_DESIGN", headline=(
                f"Geometry matches {found.design_code}, not {design.design_code}"))
        else:
            result.update(
                verdict="GEOMETRY_MATCH",
                headline=f"GEOMETRY MATCH with {found.design_code}: same shape, different file bytes",
                reasons=["SHA-256 differs from every registered file",
                         "Geometric fingerprint is identical: format conversion, re-export or "
                         "metadata-only change"])
        return result

    def watermark_check(d: Design, ver: DesignVersion) -> dict | None:
        mark = _fingerprint(db, ver.id, "watermark")
        if mark is None or (mark.meta or {}).get("status") != "applied":
            return {"detected": False, "reason": "no watermark was applied to this version"}
        return detect(triangles, _watermark_key(provider, d.design_code, ver.version))

    def can_see(d: Design) -> bool:
        return is_admin or d.owner_id == viewer.id

    if design is not None:
        current = _version_row(db, design.id, design.current_version)
        wm = watermark_check(design, current)
        result["checks"]["watermark"] = wm
        result.update(
            verdict="TAMPERED", matched_design=ref(design, current.version),
            headline=f"TAMPERED: fingerprint mismatch against {design.design_code}",
            reasons=["SHA-256 differs from the registered file",
                     "Geometric fingerprint differs from the registered geometry",
                     "Watermark of this design " + ("was found (derived from its distribution copy)"
                                                    if wm.get("detected") else "was not found")])
        if can_see(design):
            result["differences"] = compare_analysis(current.analysis, analysis)
        return result

    rows = db.execute(
        select(DesignFingerprint, DesignVersion, Design)
        .join(DesignVersion, DesignVersion.id == DesignFingerprint.design_version_id)
        .join(Design, Design.id == DesignVersion.design_id)
        .where(DesignFingerprint.kind == "watermark")
        .order_by(DesignFingerprint.id.desc()).limit(500)).all()
    best = None
    for fp, ver, d in rows:
        if (fp.meta or {}).get("status") != "applied":
            continue
        found = detect(triangles, _watermark_key(provider, d.design_code, ver.version))
        if found["detected"] and (best is None or found["score"] > best[3]["score"]):
            best = (d, ver, fp, found)
    if best:
        d, ver, _, found = best
        result["checks"]["watermark"] = found
        result.update(
            verdict="TAMPERED", matched_design=ref(d, ver.version),
            headline=f"TAMPERED: derived from {d.design_code} but modified",
            reasons=["No registered SHA-256 or geometric fingerprint matches",
                     f"The keyed watermark of {d.design_code} v{ver.version} is present "
                     f"(score {found['score']}): this copy came from the watermarked "
                     "distribution copy and was edited afterwards"])
        if can_see(d):
            result["differences"] = compare_analysis(ver.analysis, analysis)
        return result

    result.update(verdict="UNREGISTERED", headline="UNREGISTERED: no registered design matches",
                  reasons=["No SHA-256, geometric or watermark match in the design registry"])
    return result


# ---------------------------------------------------------------- 4D profiles
def _normalise_4d(values: dict) -> dict:
    clean = {k: values[k] for k in FOURD_FIELDS}
    for key in ("transformation_profile", "activation_conditions"):
        clean[key] = json.loads(canonical_json(clean[key] or {}))
    for key in ("trigger_temperature_c", "trigger_time_s"):
        clean[key] = None if clean[key] is None else float(clean[key])
    return clean


def compute_4d_fingerprint(design_code: str, design_version: int, geometric_fp: str,
                           values: dict) -> str:
    payload = {"algorithm": "SP4D1", "design_code": design_code, "design_version": design_version,
               "geometric_fingerprint": geometric_fp, **_normalise_4d(values)}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _geometric_fp_of(db: Session, design: Design, version: int) -> str:
    row = _version_row(db, design.id, version)
    fp = _fingerprint(db, row.id, "geometric") if row else None
    if fp is None:
        raise ValueError("design version has no geometric fingerprint")
    return fp.value


def set_4d_profile(db: Session, *, design: Design, user: User, values: dict) -> Design4DProfile:
    values = _normalise_4d(values)
    version = design.current_version
    fingerprint = compute_4d_fingerprint(design.design_code, version,
                                         _geometric_fp_of(db, design, version), values)
    profile = db.execute(select(Design4DProfile).where(
        Design4DProfile.design_id == design.id)).scalar_one_or_none()
    if profile is None:
        profile = Design4DProfile(design_id=design.id, created_by=user.id)
        db.add(profile)
    for key, value in values.items():
        setattr(profile, key, value)
    profile.design_version = version
    profile.security_fingerprint = fingerprint
    design.is_4d = True
    db.commit()
    db.refresh(profile)
    return profile


def verify_4d_profile(db: Session, design: Design, profile: Design4DProfile) -> dict:
    values = {f: getattr(profile, f) for f in FOURD_FIELDS}
    expected = compute_4d_fingerprint(
        design.design_code, profile.design_version,
        _geometric_fp_of(db, design, profile.design_version), values)
    intact = expected == profile.security_fingerprint
    return {"intact": intact, "expected": expected, "stored": profile.security_fingerprint,
            "design_version": profile.design_version,
            "reason": ("4D profile matches its security fingerprint" if intact else
                       "4D profile fields or the bound design geometry changed after registration")}
