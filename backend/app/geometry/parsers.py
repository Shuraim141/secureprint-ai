"""Safe parsers for STL (binary/ASCII), OBJ and 3MF. Output: float32 triangle array (n, 3, 3)
in FILE ORDER (order matters for the fragile watermark).

All input is untrusted: sizes are limited, indices are validated, 3MF uses defusedxml
(blocks XXE / entity expansion) and zip-bomb limits. Errors are GeometryError with messages
that are safe to show to users.

Known limits (MVP): OBJ materials/normals/textures ignored; 3MF build transforms and component
references are ignored (all mesh objects are merged); units are assumed to be millimetres.
Production: replace with a hardened CAD kernel/trimesh in a sandboxed worker.
"""
import io
import re
import struct
import zipfile
from dataclasses import dataclass

import numpy as np
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException


class GeometryError(ValueError):
    """Malformed, unsafe or unsupported 3D file."""


class UnsupportedFormatError(GeometryError):
    """File extension is not one of the supported 3D formats."""


@dataclass(frozen=True)
class MeshLimits:
    max_triangles: int = 500_000
    max_obj_lines: int = 3_000_000
    max_zip_entries: int = 50
    max_uncompressed_bytes: int = 200 * 1024 * 1024


DEFAULT_LIMITS = MeshLimits()  # module-level singleton: created once at import time


EXTENSIONS = {".stl": "stl", ".obj": "obj", ".3mf": "3mf"}
_STL_RECORD = np.dtype([("normal", "<f4", (3,)), ("v", "<f4", (3, 3)), ("attr", "<u2")])
_NUM = rb"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_VERTEX_RE = re.compile(rb"vertex\s+(" + _NUM + rb")\s+(" + _NUM + rb")\s+(" + _NUM + rb")")


def detect_format(filename: str, data: bytes) -> str:
    """Validate extension AND content signature. Returns 'stl' | 'obj' | '3mf'."""
    dot = filename.rfind(".")
    ext = filename[dot:].lower() if dot >= 0 else ""
    fmt = EXTENSIONS.get(ext)
    if fmt is None:
        raise UnsupportedFormatError("Unsupported file type. Allowed: .stl, .obj, .3mf")
    if not data:
        raise GeometryError("File is empty")
    if fmt == "stl":
        if not _looks_like_stl(data):
            raise GeometryError("File content is not a valid STL model")
    elif fmt == "obj":
        head = data[:200_000]
        if b"\x00" in head or not re.search(rb"(?m)^\s*v\s", head):
            raise GeometryError("File content is not a valid OBJ model")
    elif not data.startswith(b"PK\x03\x04"):
        raise GeometryError("File content is not a valid 3MF package")
    return fmt


def _looks_like_stl(data: bytes) -> bool:
    if len(data) >= 84 and 84 + 50 * struct.unpack_from("<I", data, 80)[0] == len(data):
        return True
    return data.lstrip()[:5].lower() == b"solid" and b"facet" in data[:4096] + data[-4096:]


def _finish(triangles: np.ndarray, limits: MeshLimits) -> np.ndarray:
    if len(triangles) == 0:
        raise GeometryError("Model contains no triangles")
    if len(triangles) > limits.max_triangles:
        raise GeometryError(f"Model has too many triangles (limit {limits.max_triangles})")
    triangles = np.ascontiguousarray(triangles, dtype=np.float32)
    if not np.isfinite(triangles).all():
        raise GeometryError("Model contains NaN or infinite coordinates")
    return triangles


def parse_stl(data: bytes, limits: MeshLimits = DEFAULT_LIMITS) -> np.ndarray:
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * count == len(data):
            if count > limits.max_triangles:
                raise GeometryError(f"Model has too many triangles (limit {limits.max_triangles})")
            records = np.frombuffer(data, dtype=_STL_RECORD, count=count, offset=84)
            return _finish(records["v"].copy(), limits)
    if data.lstrip()[:5].lower() != b"solid":
        raise GeometryError("STL is neither valid binary nor ASCII (size/header mismatch)")
    found = _VERTEX_RE.findall(data)
    if not found or len(found) % 3 != 0:
        raise GeometryError("ASCII STL has a missing or incomplete facet")
    if len(found) // 3 > limits.max_triangles:
        raise GeometryError(f"Model has too many triangles (limit {limits.max_triangles})")
    values = np.array(found).astype(np.float64)
    return _finish(values.reshape(-1, 3, 3), limits)


def parse_obj(data: bytes, limits: MeshLimits = DEFAULT_LIMITS) -> np.ndarray:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for line_no, raw in enumerate(data.decode("latin-1").splitlines(), start=1):
        if line_no > limits.max_obj_lines:
            raise GeometryError("OBJ file has too many lines")
        parts = raw.split()
        if not parts:
            continue
        if parts[0] == "v":
            if len(parts) < 4:
                raise GeometryError(f"OBJ line {line_no}: vertex needs 3 coordinates")
            try:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError as exc:
                raise GeometryError(f"OBJ line {line_no}: invalid vertex number") from exc
        elif parts[0] == "f":
            if len(parts) < 4:
                raise GeometryError(f"OBJ line {line_no}: face needs at least 3 vertices")
            try:
                refs = [int(token.split("/")[0]) for token in parts[1:]]
            except ValueError as exc:
                raise GeometryError(f"OBJ line {line_no}: invalid face index") from exc
            resolved = []
            for ref in refs:
                index = ref - 1 if ref > 0 else len(vertices) + ref  # negative = relative
                if ref == 0 or not 0 <= index < len(vertices):
                    raise GeometryError(f"OBJ line {line_no}: face index out of range")
                resolved.append(index)
            for k in range(1, len(resolved) - 1):  # fan triangulation of polygons
                faces.append((resolved[0], resolved[k], resolved[k + 1]))
            if len(faces) > limits.max_triangles:
                raise GeometryError(f"Model has too many triangles (limit {limits.max_triangles})")
    if not vertices or not faces:
        raise GeometryError("OBJ contains no faces")
    return _finish(np.array(vertices, dtype=np.float64)[np.array(faces)], limits)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_3mf(data: bytes, limits: MeshLimits = DEFAULT_LIMITS) -> np.ndarray:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise GeometryError("3MF is not a valid ZIP package") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_zip_entries:
            raise GeometryError("3MF package has too many entries")
        if sum(i.file_size for i in infos) > limits.max_uncompressed_bytes:
            raise GeometryError("3MF package expands to an unsafe size (zip-bomb protection)")
        model = next((i for i in infos if i.filename.lower().endswith("3d/3dmodel.model")), None)
        if model is None:
            raise GeometryError("3MF package has no 3D/3dmodel.model")
        with archive.open(model) as handle:
            xml_bytes = handle.read(limits.max_uncompressed_bytes + 1)
        if len(xml_bytes) > limits.max_uncompressed_bytes:
            raise GeometryError("3MF model part is too large")
    try:
        root = SafeET.fromstring(xml_bytes)
    except DefusedXmlException as exc:
        raise GeometryError("3MF contains unsafe XML (DTD/entities are not allowed)") from exc
    except SafeET.ParseError as exc:
        raise GeometryError("3MF model XML is malformed") from exc

    chunks = []
    for mesh in (el for el in root.iter() if _local(el.tag) == "mesh"):
        verts, tris = [], []
        for el in mesh.iter():
            name = _local(el.tag)
            try:
                if name == "vertex":
                    verts.append((float(el.get("x")), float(el.get("y")), float(el.get("z"))))
                elif name == "triangle":
                    tris.append((int(el.get("v1")), int(el.get("v2")), int(el.get("v3"))))
            except (TypeError, ValueError) as exc:
                raise GeometryError("3MF mesh has an invalid vertex or triangle") from exc
        if not verts or not tris:
            continue
        index = np.array(tris)
        if index.min() < 0 or index.max() >= len(verts):
            raise GeometryError("3MF triangle refers to a missing vertex")
        chunks.append(np.array(verts, dtype=np.float64)[index])
        if sum(len(c) for c in chunks) > limits.max_triangles:
            raise GeometryError(f"Model has too many triangles (limit {limits.max_triangles})")
    if not chunks:
        raise GeometryError("3MF contains no mesh")
    return _finish(np.concatenate(chunks), limits)


def parse_mesh(data: bytes, fmt: str, limits: MeshLimits = DEFAULT_LIMITS) -> np.ndarray:
    parsers = {"stl": parse_stl, "obj": parse_obj, "3mf": parse_3mf}
    if fmt not in parsers:
        raise UnsupportedFormatError("Unsupported file type")
    return parsers[fmt](data, limits)
