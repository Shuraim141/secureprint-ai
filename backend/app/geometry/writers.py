"""Mesh file writers (binary/ASCII STL, OBJ, 3MF). Used for the watermarked distribution copy,
the demo scripts and tests."""
import io
import struct
import zipfile

import numpy as np


def _normals(tri: np.ndarray) -> np.ndarray:
    n = np.cross(tri[:, 1].astype(np.float64) - tri[:, 0], tri[:, 2].astype(np.float64) - tri[:, 0])
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return (n / np.where(length == 0, 1, length)).astype(np.float32)


def write_binary_stl(tri: np.ndarray, header: bytes = b"SecurePrint AI demo model") -> bytes:
    tri = np.ascontiguousarray(tri, dtype=np.float32)
    record = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])
    body = np.zeros(len(tri), dtype=record)
    body["n"], body["v"] = _normals(tri), tri
    return header[:80].ljust(80, b" ") + struct.pack("<I", len(tri)) + body.tobytes()


def write_ascii_stl(tri: np.ndarray, name: str = "model") -> bytes:
    lines = [f"solid {name}"]
    for t, n in zip(tri, _normals(tri), strict=True):
        lines.append(f"facet normal {n[0]:.9g} {n[1]:.9g} {n[2]:.9g}\n outer loop")
        lines += [f"  vertex {v[0]:.9g} {v[1]:.9g} {v[2]:.9g}" for v in t]
        lines.append(" endloop\nendfacet")
    lines.append(f"endsolid {name}")
    return ("\n".join(lines) + "\n").encode("ascii")


def _indexed(tri: np.ndarray):
    flat = np.ascontiguousarray(tri, dtype=np.float32).reshape(-1, 3)
    unique, inverse = np.unique(flat, axis=0, return_inverse=True)
    return unique, inverse.reshape(-1).reshape(-1, 3)


def write_obj(tri: np.ndarray) -> bytes:
    verts, faces = _indexed(tri)
    lines = ["# SecurePrint AI demo model"]
    lines += [f"v {x:.9g} {y:.9g} {z:.9g}" for x, y, z in verts]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    return ("\n".join(lines) + "\n").encode("ascii")


def write_3mf(tri: np.ndarray) -> bytes:
    verts, faces = _indexed(tri)
    vertex_xml = "".join(f'<vertex x="{x:.9g}" y="{y:.9g}" z="{z:.9g}"/>' for x, y, z in verts)
    tri_xml = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        f'<resources><object id="1" type="model"><mesh><vertices>{vertex_xml}</vertices>'
        f'<triangles>{tri_xml}</triangles></mesh></object></resources>'
        '<build><item objectid="1"/></build></model>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("3D/3dmodel.model", model)
    return buffer.getvalue()
