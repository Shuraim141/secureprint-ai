"""FRAGILE keyed watermark for triangle meshes (prototype).

Idea: hide a 64-bit owner tag in the least-significant mantissa bit of float32 vertex
coordinates at secret, key-derived positions (a coordinate changes by at most 1 ulp, about
1e-7 relative, i.e. invisible for printing). Detection reads the same positions.

This is NOT the same thing as a hash/fingerprint: a fingerprint identifies a file or shape, a
watermark carries an owner tag inside the data itself and can show that a copy derives from a
watermarked distribution copy even after small edits.

Limits (honest): survives lossless float32 copies (binary STL, ASCII with 9 significant
digits) and small local edits. Destroyed by re-ordering triangles, rounding coordinates,
scaling/rotating, re-meshing or slicing. Attackers who know the algorithm and have the key can
forge it; without the key they cannot locate the bits. Production: robust mesh-watermarking
research methods (spectral/geometric) and a secrets manager.
"""
import hashlib
import hmac

import numpy as np

TAG_BITS = 64
MIN_COORDS = 256
MAX_SAMPLES = 4096
DETECTION_THRESHOLD = 0.8


class WatermarkCapacityError(ValueError):
    """Model has too few coordinates to carry the watermark."""


def derive_tag(key: bytes) -> bytes:
    """8-byte tag from the key, re-derived until it has a balanced number of 1 bits."""
    for counter in range(256):
        tag = hmac.new(key, b"tag" + bytes([counter]), hashlib.sha256).digest()[:8]
        if 24 <= bin(int.from_bytes(tag, "big")).count("1") <= 40:
            return tag
    raise RuntimeError("could not derive a balanced watermark tag")  # pragma: no cover


def _positions_and_bits(key: bytes, n_coords: int) -> tuple[np.ndarray, np.ndarray]:
    if n_coords < MIN_COORDS:
        raise WatermarkCapacityError(
            f"Model too small for the watermark (needs at least {MIN_COORDS // 9 + 1} triangles)"
        )
    seed = int.from_bytes(hmac.new(key, b"positions", hashlib.sha256).digest()[:16], "big")
    raw = np.random.PCG64(seed).random_raw(n_coords)  # BitGenerator stream is version-stable
    samples = min(n_coords, MAX_SAMPLES)
    samples -= samples % TAG_BITS
    positions = np.argsort(raw, kind="stable")[:samples]
    tag_bits = np.unpackbits(np.frombuffer(derive_tag(key), dtype=np.uint8))
    return positions, tag_bits[np.arange(samples) % TAG_BITS]


def embed(triangles: np.ndarray, key: bytes) -> tuple[np.ndarray, dict]:
    original = np.ascontiguousarray(triangles, dtype=np.float32)
    flat = original.reshape(-1)
    positions, bits = _positions_and_bits(key, flat.size)
    words = flat.view(np.uint32).copy()
    words[positions] = (words[positions] & np.uint32(0xFFFFFFFE)) | bits.astype(np.uint32)
    marked = words.view(np.float32).reshape(original.shape)
    change = np.abs(marked.astype(np.float64) - original.astype(np.float64))
    return marked, {
        "tag_hex": derive_tag(key).hex(),
        "samples": int(len(positions)),
        "changed_coordinates": int((change > 0).sum()),
        "max_abs_change": float(change.max()),
    }


def detect(triangles: np.ndarray, key: bytes) -> dict:
    """Score how strongly `key`'s watermark is present. Uses min(P[1 where 1], P[0 where 0])
    so meshes whose LSBs are naturally biased (grid-aligned CAD) cannot fake a match."""
    flat = np.ascontiguousarray(triangles, dtype=np.float32).reshape(-1)
    try:
        positions, bits = _positions_and_bits(key, flat.size)
    except WatermarkCapacityError as exc:
        return {"detected": False, "score": 0.0, "samples": 0, "reason": str(exc)}
    observed = (flat.view(np.uint32)[positions] & 1).astype(np.uint8)
    ones, zeros = bits == 1, bits == 0
    p_ones = float((observed[ones] == 1).mean())
    p_zeros = float((observed[zeros] == 0).mean())
    score = min(p_ones, p_zeros)
    return {"detected": score >= DETECTION_THRESHOLD, "score": round(score, 4),
            "p_ones": round(p_ones, 4), "p_zeros": round(p_zeros, 4),
            "samples": int(len(positions))}
