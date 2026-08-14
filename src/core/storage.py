"""Deterministic local raw object storage helpers."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path, PurePosixPath, PureWindowsPath


class RawObjectAlreadyExistsError(FileExistsError):
    pass


def _encode_windows_physical_part(part: str) -> str:
    marker = "~raw~"
    forbidden = '<>:"|?*'
    stem = part.split(".", 1)[0].upper()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
    }
    needs_encoding = (
        any(character in forbidden or ord(character) < 32 for character in part)
        or part.endswith((" ", "."))
        or stem in reserved
        or part.startswith(marker)
    )
    if not needs_encoding:
        return part
    trailing_start = len(part.rstrip(" ."))
    encoded_parts: list[str] = []
    for index, character in enumerate(part):
        must_encode = (
            character in forbidden
            or character == "%"
            or ord(character) < 32
            or (index >= trailing_start and character in " .")
            or (part.startswith(marker) and character == "~")
        )
        encoded_parts.append(f"%{ord(character):02X}" if must_encode else character)
    return marker + "".join(encoded_parts)


def _read_concurrent_winner(path: Path) -> bytes:
    for attempt in range(50):
        try:
            return path.read_bytes()
        except (FileNotFoundError, PermissionError):
            if attempt == 49:
                raise
            time.sleep(0.002)
    raise RuntimeError("unreachable concurrent RAW read state")


class RawObjectStore:
    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def object_path(self, object_key: str) -> Path:
        parts = self._validated_parts(object_key)
        physical_parts = (
            [self._windows_physical_part(part) for part in parts] if os.name == "nt" else parts
        )
        return self._bounded_path(physical_parts)

    def _legacy_object_path(self, object_key: str) -> Path:
        return self._bounded_path(self._validated_parts(object_key))

    @staticmethod
    def _validated_parts(object_key: str) -> list[str]:
        if not object_key or "\x00" in object_key:
            raise ValueError("Object key must be a non-empty relative path")
        if PurePosixPath(object_key).is_absolute() or PureWindowsPath(object_key).is_absolute():
            raise ValueError("Absolute object keys are not allowed")

        parts = object_key.replace("\\", "/").split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Object key contains an unsafe path segment")
        return parts

    def _bounded_path(self, parts: list[str]) -> Path:
        target = Path(os.path.abspath(self.base_path.joinpath(*parts)))
        if target == self.base_path or os.path.commonpath((self.base_path, target)) != str(
            self.base_path
        ):
            raise ValueError("Object key resolves outside the RAW object store")
        candidate = self.base_path
        for part in parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError("Object key traverses a symbolic link")
        return target

    @staticmethod
    def _windows_physical_part(part: str) -> str:
        return _encode_windows_physical_part(part)

    def write_bytes(self, object_key: str, content: bytes) -> Path:
        path = self.object_path(object_key)
        if os.name == "nt":
            legacy_path = self._legacy_object_path(object_key)
            if legacy_path != path and legacy_path.exists():
                if legacy_path.read_bytes() != content:
                    raise RawObjectAlreadyExistsError(
                        f"RAW object already exists with conflicting bytes: {object_key}"
                    )
                return legacy_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=".raw-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if os.name == "nt":
                os.rename(temporary, path)
            else:
                os.link(temporary, path)
        except FileExistsError as exc:
            if _read_concurrent_winner(path) != content:
                raise RawObjectAlreadyExistsError(
                    f"RAW object already exists with conflicting bytes: {object_key}"
                ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path

    def read_bytes(self, object_key: str) -> bytes:
        path = self.object_path(object_key)
        if os.name == "nt" and not path.exists():
            legacy_path = self._legacy_object_path(object_key)
            if legacy_path != path and legacy_path.exists():
                path = legacy_path
        return path.read_bytes()
