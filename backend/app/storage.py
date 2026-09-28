"""File storage abstraction. MVP: local directory. Production: S3/object storage adapter."""
import os
import re
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

_KEY_RE = re.compile(r"^[a-f0-9]{32}\.enc$")


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def load(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...


class LocalFileStorage(StorageBackend):
    """Keys must be generated names (32 hex chars + .enc); anything else is rejected, so user
    input can never influence the path (path-traversal protection)."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _KEY_RE.match(key):
            raise ValueError("invalid storage key")
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("invalid storage key")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        fd, tmp_name = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, path)  # atomic
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()
