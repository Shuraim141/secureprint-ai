"""Pure-logic tests for 3D parsing, analysis, fingerprinting, watermarking, encryption, uploads
and storage. No web framework or database is used, so these run everywhere."""
import io
import math
import os
import struct
import tempfile
import zipfile
from pathlib import Path

import numpy as np

from app.geometry import samples
from app.geometry.analysis import analyze_mesh, geometric_fingerprint
from app.geometry.parsers import (
    GeometryError,
    MeshLimits,
    UnsupportedFormatError,
    detect_format,
    parse_3mf,
    parse_mesh,
)
from app.geometry.watermark import WatermarkCapacityError, detect, embed
from app.security.crypto import CryptoError, LocalKeyProvider, decrypt_bytes, encrypt_bytes
from app.security.uploads import UploadTooLarge, read_limited, sanitize_display_name
from app.storage import LocalFileStorage

KEY = bytes(range(32))
OTHER_KEY = bytes(range(32, 64))


def raises(exc_type, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except exc_type as error:
        return error
    raise AssertionError(f"expected {exc_type.__name__}")


# ---------------- analysis correctness ----------------
def test_box_analysis_matches_known_values():
    info = analyze_mesh(samples.make_box((60, 30, 10), (8, 4, 2)))
    assert info["triangle_count"] == 224
    assert info["vertex_count"] == 114  # 9*5*3 grid points minus 21 interior ones
    assert info["dimensions_mm"] == {"x": 60.0, "y": 30.0, "z": 10.0}
    assert abs(info["volume_mm3"] - 18000.0) < 1e-3
    assert abs(info["surface_area_mm2"] - 2 * (60 * 30 + 60 * 10 + 30 * 10)) < 1e-3
    assert info["watertight"] and info["volume_reliable"] and info["warnings"] == []
    assert info["vertex_count"] - 336 + info["triangle_count"] == 2  # Euler characteristic


def test_cylinder_and_sphere_volumes():
    cyl = analyze_mesh(samples.make_cylinder(6.0, 40.0, 32, 4))
    expected = 0.5 * 32 * 36.0 * math.sin(2 * math.pi / 32) * 40.0
    assert cyl["watertight"] and abs(cyl["volume_mm3"] - expected) / expected < 1e-4
    sph = analyze_mesh(samples.make_sphere(20.0, 16, 32))
    ideal = 4 / 3 * math.pi * 20.0**3
    assert sph["watertight"] and abs(sph["volume_mm3"] - ideal) / ideal < 0.05


def test_open_mesh_and_degenerate_triangles_are_reported():
    tri = samples.make_box()
    info = analyze_mesh(tri[1:])
    assert not info["watertight"] and info["open_edges"] == 3
    assert any("not watertight" in w for w in info["warnings"])
    flat = np.concatenate([tri, tri[:1, [0, 0, 0]]])
    assert analyze_mesh(flat)["degenerate_triangles"] == 1


def test_inverted_normals_are_flagged():
    inverted = samples.make_box()[:, ::-1, :]
    info = analyze_mesh(np.ascontiguousarray(inverted))
    assert any("inward" in w for w in info["warnings"])


# ---------------- parsers ----------------
def test_all_formats_roundtrip_to_same_geometry():
    tri = samples.make_cylinder()
    reference = geometric_fingerprint(tri)
    binary = samples.write_binary_stl(tri)
    assert np.array_equal(parse_mesh(binary, "stl"), tri)  # binary keeps exact order/values
    for name, data in [("m.stl", binary), ("m.stl", samples.write_ascii_stl(tri)),
                       ("m.obj", samples.write_obj(tri)), ("m.3mf", samples.write_3mf(tri))]:
        parsed = parse_mesh(data, detect_format(name, data))
        assert geometric_fingerprint(parsed) == reference, name


def test_format_detection_rejects_bad_input():
    stl = samples.write_binary_stl(samples.make_box())
    raises(UnsupportedFormatError, detect_format, "virus.exe", stl)
    raises(UnsupportedFormatError, detect_format, "noextension", stl)
    raises(GeometryError, detect_format, "fake.stl", b"hello this is not a model")
    raises(GeometryError, detect_format, "fake.obj", b"\x00\x01\x02binary")
    raises(GeometryError, detect_format, "fake.3mf", b"not a zip")
    raises(GeometryError, detect_format, "empty.stl", b"")
    raises(GeometryError, detect_format, "truncated.stl", stl[:-30])


def test_stl_with_nan_and_limits_is_rejected():
    tri = samples.make_box().copy()
    tri[0, 0, 0] = np.nan
    raises(GeometryError, parse_mesh, samples.write_binary_stl(tri), "stl")
    raises(GeometryError, parse_mesh, samples.write_binary_stl(samples.make_box()), "stl",
           MeshLimits(max_triangles=10))
    liar = bytearray(samples.write_binary_stl(samples.make_box()))
    struct.pack_into("<I", liar, 80, 4_000_000_000)  # header claims 4 billion triangles
    raises(GeometryError, parse_mesh, bytes(liar), "stl")


def test_obj_quads_negative_indices_and_bad_indices():
    quad = b"v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n"
    assert len(parse_mesh(quad, "obj")) == 2  # quad -> 2 triangles
    relative = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf -3 -2 -1\n"
    assert len(parse_mesh(relative, "obj")) == 1
    raises(GeometryError, parse_mesh, b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 9\n", "obj")
    raises(GeometryError, parse_mesh, b"v 0 0 abc\nf 1 1 1\n", "obj")
    raises(GeometryError, parse_mesh, b"v 0 0 0\n", "obj")


def test_3mf_blocks_xxe_and_zip_bombs():
    xxe = (b'<?xml version="1.0"?><!DOCTYPE m [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
           b'<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">&x;</model>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("3D/3dmodel.model", xxe)
    error = raises(GeometryError, parse_3mf, buffer.getvalue())
    assert "unsafe" in str(error)

    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("3D/3dmodel.model", b"0" * 5_000_000)
    raises(GeometryError, parse_3mf, bomb.getvalue(), MeshLimits(max_uncompressed_bytes=1_000_000))

    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("other.txt", b"x")
    raises(GeometryError, parse_3mf, empty.getvalue())


# ---------------- geometric fingerprint ----------------
def test_fingerprint_invariance_and_sensitivity():
    tri = samples.make_box()
    base = geometric_fingerprint(tri)
    rng = np.random.default_rng(1)
    shuffled = tri[rng.permutation(len(tri))]
    rotated = shuffled[:, [1, 2, 0], :]  # cyclic vertex rotation keeps winding
    assert geometric_fingerprint(rotated) == base
    moved = samples.tamper_mesh(tri, 0.5)
    assert geometric_fingerprint(moved) != base
    assert geometric_fingerprint(tri[:-1]) != base            # removed triangle
    assert geometric_fingerprint(tri[:, ::-1, :]) != base      # flipped winding
    assert len(base) == 64


# ---------------- watermark ----------------
def test_watermark_embed_detect_and_limits():
    tri = samples.make_box()
    marked, info = embed(tri, KEY)
    assert info["max_abs_change"] < 1e-4 and info["samples"] == 1984
    assert detect(marked, KEY)["detected"] and detect(marked, KEY)["score"] == 1.0
    assert not detect(tri, KEY)["detected"]          # original carries no mark
    assert not detect(marked, OTHER_KEY)["detected"]  # wrong key cannot find it
    ascii_copy = parse_mesh(samples.write_ascii_stl(marked), "stl")
    assert detect(ascii_copy, KEY)["detected"]        # survives lossless ASCII copy


def test_watermark_is_fragile_by_design():
    tri = samples.make_cylinder()
    marked, _ = embed(tri, KEY)
    edited = samples.tamper_mesh(marked, 0.5)
    assert detect(edited, KEY)["detected"]            # small local edit: still found
    rng = np.random.default_rng(2)
    assert not detect(marked[rng.permutation(len(marked))], KEY)["detected"]  # reorder destroys
    assert not detect(np.round(marked, 3).astype(np.float32), KEY)["detected"]  # rounding destroys
    assert not detect(marked * np.float32(1.01), KEY)["detected"]               # scaling destroys


def test_watermark_needs_capacity():
    tiny = samples.make_box((10, 10, 10), (1, 1, 1))  # 12 triangles
    raises(WatermarkCapacityError, embed, tiny, KEY)
    assert detect(tiny, KEY)["detected"] is False


def test_watermark_embedding_is_deterministic():
    tri = samples.make_box()
    a, _ = embed(tri, KEY)
    b, _ = embed(tri, KEY)
    assert samples.write_binary_stl(a) == samples.write_binary_stl(b)


# ---------------- encryption ----------------
def test_encryption_roundtrip_and_tamper_detection():
    provider = LocalKeyProvider(KEY)
    secret = b"proprietary aerospace bracket geometry" * 100
    blob = encrypt_bytes(secret, aad=b"abc.enc", key_provider=provider)
    assert secret[:20] not in blob.ciphertext and len(blob.ciphertext) == len(secret) + 16
    ok = decrypt_bytes(blob.ciphertext, nonce=blob.nonce, wrapped_key=blob.wrapped_key,
                       aad=b"abc.enc", key_provider=provider)
    assert ok == secret
    again = encrypt_bytes(secret, aad=b"abc.enc", key_provider=provider)
    assert again.ciphertext != blob.ciphertext and again.wrapped_key != blob.wrapped_key

    flipped = bytearray(blob.ciphertext)
    flipped[10] ^= 1
    kwargs = dict(nonce=blob.nonce, wrapped_key=blob.wrapped_key, aad=b"abc.enc", key_provider=provider)
    raises(CryptoError, decrypt_bytes, bytes(flipped), **kwargs)
    raises(CryptoError, decrypt_bytes, blob.ciphertext, **{**kwargs, "aad": b"other.enc"})
    wrong_key = {**kwargs, "key_provider": LocalKeyProvider(OTHER_KEY)}
    raises(CryptoError, decrypt_bytes, blob.ciphertext, **wrong_key)
    raises(ValueError, LocalKeyProvider, b"short")


def test_subkeys_are_purpose_separated():
    provider = LocalKeyProvider(KEY)
    assert provider.derive_subkey("a") != provider.derive_subkey("b")
    assert provider.derive_subkey("a") == LocalKeyProvider(KEY).derive_subkey("a")
    assert provider.derive_subkey("a") != KEY


# ---------------- uploads and storage ----------------
def test_display_name_sanitising_blocks_path_tricks():
    assert sanitize_display_name("../../etc/passwd.stl") == "passwd.stl"
    assert sanitize_display_name("C:\\Users\\x\\evil.stl") == "evil.stl"
    assert sanitize_display_name("a\x00b\r\n.stl") == "a_b__.stl"
    assert sanitize_display_name("") == "upload" and sanitize_display_name(None) == "upload"
    assert sanitize_display_name("..") == "upload"
    assert len(sanitize_display_name("x" * 500 + ".stl")) == 120
    assert "/" not in sanitize_display_name("a/b\\c.stl")


def test_read_limited_stops_oversize_uploads():
    assert read_limited(io.BytesIO(b"x" * 100), 100) == b"x" * 100
    raises(UploadTooLarge, read_limited, io.BytesIO(b"x" * 101), 100)


def test_storage_rejects_traversal_and_uses_private_files():
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalFileStorage(Path(tmp) / "designs")
        key = "a" * 32 + ".enc"
        store.save(key, b"ciphertext")
        assert store.load(key) == b"ciphertext" and store.exists(key)
        assert oct(os.stat(Path(tmp) / "designs" / key).st_mode & 0o777) == "0o600"
        for bad in ["../evil.enc", "/etc/passwd", "a" * 32, "A" * 32 + ".enc", "x/y.enc", ""]:
            raises(ValueError, store.save, bad, b"x")
            raises(ValueError, store.load, bad)
        store.delete(key)
        assert not store.exists(key)
