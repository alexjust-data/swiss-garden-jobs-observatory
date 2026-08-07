"""Deterministic local raw object storage helpers."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


class RawObjectAlreadyExistsError(FileExistsError):
    pass


class RawObjectStore:
    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def object_path(self, object_key: str) -> Path:
        if not object_key or "\x00" in object_key:
            raise ValueError("Object key must be a non-empty relative path")
        if PurePosixPath(object_key).is_absolute() or PureWindowsPath(object_key).is_absolute():
            raise ValueError("Absolute object keys are not allowed")

        parts = object_key.replace("\\", "/").split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Object key contains an unsafe path segment")

        target = (self.base_path / Path(*parts)).resolve()
        if target == self.base_path or not target.is_relative_to(self.base_path):
            raise ValueError("Object key resolves outside the RAW object store")
        return target

    def write_bytes(self, object_key: str, content: bytes) -> Path:
        path = self.object_path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(content)
        except FileExistsError as exc:
            raise RawObjectAlreadyExistsError(
                f"RAW object already exists and cannot be overwritten: {object_key}"
            ) from exc
        return path

    def read_bytes(self, object_key: str) -> bytes:
        path = self.object_path(object_key)
        return path.read_bytes()
