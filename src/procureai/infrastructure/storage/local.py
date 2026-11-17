"""Local file storage. Files are stored under generated keys, never under user-supplied names."""

from __future__ import annotations

import hashlib
from pathlib import Path

from procureai.shared.errors import NotFoundError, ProcessingError
from procureai.shared.types import new_id


class LocalFileStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root != path and self.root not in path.parents:  # path-traversal guard
            raise ProcessingError("Invalid storage key.")
        return path

    def save(self, data: bytes, suffix: str = "", prefix: str = "") -> tuple[str, str]:
        """Persist bytes; returns (storage_key, sha256)."""
        suffix = suffix if suffix.startswith(".") or not suffix else f".{suffix}"
        key = f"{prefix}{new_id()}{suffix.lower()}"
        path = self._resolve(key)
        path.write_bytes(data)
        return key, hashlib.sha256(data).hexdigest()

    def path_for(self, key: str) -> Path:
        path = self._resolve(key)
        if not path.exists():
            raise NotFoundError("Stored file was not found.")
        return path

    def read(self, key: str) -> bytes:
        return self.path_for(key).read_bytes()

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def writable(self) -> bool:
        probe = self.root / f".probe-{new_id()}"
        try:
            probe.write_bytes(b"ok")
            probe.unlink()
            return True
        except OSError:
            return False
