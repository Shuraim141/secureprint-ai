"""Upload hygiene: safe display names and size-limited reads."""
import re
import unicodedata
from typing import BinaryIO

_ALLOWED = re.compile(r"[^A-Za-z0-9._() -]")


class UploadTooLarge(Exception):
    pass


def sanitize_display_name(name: str | None, default: str = "upload") -> str:
    """Return a harmless display name: no directories, no control chars, limited charset.
    It is stored for display only. Files on disk always get generated names."""
    text = unicodedata.normalize("NFKC", (name or "")).replace("\\", "/").split("/")[-1]
    text = _ALLOWED.sub("_", text).strip(" .")
    return (text or default)[:120]


def read_limited(handle: BinaryIO, max_bytes: int) -> bytes:
    """Read at most max_bytes; raise UploadTooLarge as soon as the limit is exceeded."""
    chunks, total = [], 0
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLarge(f"File exceeds the {max_bytes // (1024 * 1024)} MB limit")
        chunks.append(chunk)
    return b"".join(chunks)
