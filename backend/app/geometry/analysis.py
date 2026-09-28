"""Geometry analysis and the geometric fingerprint (NumPy only, computed from real vertices).

Units are assumed to be millimetres (STL/OBJ carry no units).
"""
import hashlib

import numpy as np

ANALYSIS_QUANTUM_MM = 1e-3   # vertices closer than this are treated as the same vertex
GEOMETRY_QUANTUM_MM = 5e-3   # fingerprint bucket size (5 micrometres)


def _round(value: float) -> float:
    return round(float(value), 6)


def analyze_mesh(triangles: np.ndarray) -> dict:
    t = np.asarray(triangles, dtype=np.float64)
    n = len(t)
    flat = t.reshape(-1, 3)
    mins, maxs = flat.min(axis=0), flat.max(axis=0)
    dims = maxs - mins

    quantized = np.rint(flat / ANALYSIS_QUANTUM_MM).astype(np.int64)
    unique_vertices, inverse = np.unique(quantized, axis=0, return_inverse=True)
    ids = inverse.reshape(-1).reshape(n, 3)

    cross = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    repeated = (ids[:, 0] == ids[:, 1]) | (ids[:, 1] == ids[:, 2]) | (ids[:, 2] == ids[:, 0])
    degenerate = repeated | (areas < 1e-12)
    good = ~degenerate

    signed_volume = float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)

    g = ids[good]
    directed = np.concatenate([g[:, [0, 1]], g[:, [1, 2]], g[:, [2, 0]]])
    undirected = np.sort(directed, axis=1)
    _, counts = np.unique(undirected, axis=0, return_counts=True)
    open_edges = int((counts == 1).sum())
    non_manifold_edges = int((counts > 2).sum())
    keys = directed[:, 0].astype(np.int64) * len(unique_vertices) + directed[:, 1]
    inconsistent_edges = int(len(keys) - len(np.unique(keys)))
    watertight = open_edges == 0 and non_manifold_edges == 0 and len(g) > 0
    reliable = watertight and inconsistent_edges == 0

    warnings = []
    if open_edges:
        warnings.append(f"Mesh is not watertight: {open_edges} open edge(s)")
    if non_manifold_edges:
        warnings.append(f"{non_manifold_edges} non-manifold edge(s)")
    if int(degenerate.sum()):
        warnings.append(f"{int(degenerate.sum())} degenerate triangle(s)")
    if inconsistent_edges:
        warnings.append(f"Inconsistent triangle orientation on {inconsistent_edges} edge(s)")
    if reliable and signed_volume < 0:
        warnings.append("Negative signed volume: triangle normals point inward")
    if float(dims.max()) < 1.0:
        warnings.append("Model is smaller than 1 mm: check units (assumed mm)")
    if float(dims.max()) > 1000.0:
        warnings.append("Model is larger than 1000 mm: check units (assumed mm)")

    return {
        "units_assumed": "mm",
        "triangle_count": int(n),
        "vertex_count": int(len(unique_vertices)),
        "bounding_box_min": [_round(v) for v in mins],
        "bounding_box_max": [_round(v) for v in maxs],
        "dimensions_mm": {"x": _round(dims[0]), "y": _round(dims[1]), "z": _round(dims[2])},
        "surface_area_mm2": _round(areas.sum()),
        "volume_mm3": _round(abs(signed_volume)),
        "volume_reliable": bool(reliable),
        "watertight": bool(watertight),
        "open_edges": open_edges,
        "non_manifold_edges": non_manifold_edges,
        "degenerate_triangles": int(degenerate.sum()),
        "inconsistent_edges": inconsistent_edges,
        "valid": bool(len(g) > 0),
        "warnings": warnings,
    }


def _lex_less(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    diff = a - b
    nonzero = diff != 0
    first = nonzero.argmax(axis=1)
    picked = diff[np.arange(len(diff)), first]
    return nonzero.any(axis=1) & (picked < 0)


def geometric_fingerprint(triangles: np.ndarray) -> str:
    """SHA-256 over canonicalised geometry (label SPGF1).

    Canonical form: vertices quantised to GEOMETRY_QUANTUM_MM; each triangle rotated so its
    smallest vertex comes first (winding preserved); triangles sorted lexicographically.
    Invariant to: file format, triangle order, which vertex a facet starts with, float noise
    below the bucket size. NOT invariant to translation, rotation or scaling, and a coordinate
    sitting exactly on a bucket boundary can flip after a lossy re-export (treat a missing
    geometric match as inconclusive, a present match as strong evidence).
    """
    q = np.rint(np.asarray(triangles, dtype=np.float64) / GEOMETRY_QUANTUM_MM).astype(np.int64)
    n = len(q)
    smallest = np.zeros(n, dtype=np.int64)
    current = q[:, 0].copy()
    for k in (1, 2):
        better = _lex_less(q[:, k], current)
        smallest[better] = k
        current[better] = q[better, k]
    rotation = (smallest[:, None] + np.arange(3)[None, :]) % 3
    rotated = np.take_along_axis(q, rotation[:, :, None], axis=1).reshape(n, 9)
    ordered = rotated[np.lexsort(rotated.T[::-1])]
    digest = hashlib.sha256(b"SPGF1")
    digest.update(np.ascontiguousarray(ordered, dtype="<i8").tobytes())
    return digest.hexdigest()
