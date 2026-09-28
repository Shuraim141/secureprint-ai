"""Procedural demo meshes and file writers (used by the demo scripts and by tests).

These are simple watertight primitives (box, cylinder, sphere), NOT real engineering parts.
"""
import numpy as np

from app.geometry.writers import write_3mf, write_ascii_stl, write_binary_stl, write_obj

__all__ = ["make_box", "make_cylinder", "make_sphere", "tamper_mesh", "write_3mf",
           "write_ascii_stl", "write_binary_stl", "write_obj"]


def _grid_face(axes: dict, fixed: str, end: int, axis_u: str, axis_v: str) -> list:
    """Triangles for one box face; (u x v) points outward. Shared edges reuse exact values."""
    us, vs, level = axes[axis_u], axes[axis_v], axes[fixed][end]

    def point(a: int, b: int) -> tuple:
        p = {fixed: level, axis_u: us[a], axis_v: vs[b]}
        return (p["x"], p["y"], p["z"])

    out = []
    for i in range(len(us) - 1):
        for j in range(len(vs) - 1):
            p00, p10, p11, p01 = point(i, j), point(i + 1, j), point(i + 1, j + 1), point(i, j + 1)
            out += [(p00, p10, p11), (p00, p11, p01)]
    return out


def make_box(size=(60.0, 30.0, 10.0), divisions=(8, 4, 2)) -> np.ndarray:
    xs, ys, zs = (np.linspace(0.0, s, d + 1) for s, d in zip(size, divisions, strict=True))
    axes = {"x": xs, "y": ys, "z": zs}
    faces = [("z", -1, "x", "y"), ("z", 0, "y", "x"), ("x", -1, "y", "z"),
             ("x", 0, "z", "y"), ("y", -1, "z", "x"), ("y", 0, "x", "z")]
    triangles = []
    for fixed, end, axis_u, axis_v in faces:
        triangles += _grid_face(axes, fixed, end, axis_u, axis_v)
    return np.array(triangles, dtype=np.float32)


def make_cylinder(radius=6.0, height=40.0, segments=32, rings=4) -> np.ndarray:
    theta = 2.0 * np.pi * np.arange(segments) / segments
    xs, ys = radius * np.cos(theta), radius * np.sin(theta)
    zs = np.linspace(0.0, height, rings + 1)
    tris = []
    for k in range(rings):
        for i in range(segments):
            j = (i + 1) % segments
            a, b = (xs[i], ys[i], zs[k]), (xs[j], ys[j], zs[k])
            c, d = (xs[j], ys[j], zs[k + 1]), (xs[i], ys[i], zs[k + 1])
            tris += [(a, b, c), (a, c, d)]
    for i in range(segments):
        j = (i + 1) % segments
        bottom, top = (0.0, 0.0, zs[0]), (0.0, 0.0, zs[-1])
        tris.append((bottom, (xs[j], ys[j], zs[0]), (xs[i], ys[i], zs[0])))
        tris.append((top, (xs[i], ys[i], zs[-1]), (xs[j], ys[j], zs[-1])))
    return np.array(tris, dtype=np.float32)


def make_sphere(radius=20.0, n_lat=12, n_lon=24) -> np.ndarray:
    phi = np.pi * np.arange(n_lat + 1) / n_lat
    theta = 2.0 * np.pi * np.arange(n_lon) / n_lon
    grid = np.zeros((n_lat + 1, n_lon, 3))
    for j in range(n_lat + 1):
        for i in range(n_lon):
            grid[j, i] = (radius * np.sin(phi[j]) * np.cos(theta[i]),
                          radius * np.sin(phi[j]) * np.sin(theta[i]), radius * np.cos(phi[j]))
    grid[0], grid[n_lat] = (0.0, 0.0, radius), (0.0, 0.0, -radius)  # exact poles
    tris = []
    for j in range(n_lat):
        for i in range(n_lon):
            a, b = grid[j, i], grid[j, (i + 1) % n_lon]
            c, d = grid[j + 1, (i + 1) % n_lon], grid[j + 1, i]
            if j != n_lat - 1:
                tris.append((a, d, c))
            if j != 0:
                tris.append((a, c, b))
    return np.array(tris, dtype=np.float32)


def tamper_mesh(tri: np.ndarray, shift_mm: float = 0.5) -> np.ndarray:
    """Simulated design attack: push the vertices on the +X extreme outward by shift_mm."""
    out = np.array(tri, dtype=np.float32, copy=True)
    limit = out[:, :, 0].max() - 1e-3
    out[:, :, 0][out[:, :, 0] >= limit] += np.float32(shift_mm)
    return out
