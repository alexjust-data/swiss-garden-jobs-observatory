"""Deterministic local raw object storage helpers."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path, PurePosixPath, PureWindowsPath


class RawObjectAlreadyExistsError(FileExistsError):
    pass


WINDOWS_PHYSICAL_PREFIX = "~raw~"
WINDOWS_MAX_COMPONENT_LENGTH = 255


def _encode_windows_physical_part(part: str) -> str:
    """Encode one logical component injectively under Windows name folding.

    Canonical lower-case ASCII components remain compact. Every component that
    could alias after Windows case folding or filename normalization receives a
    reserved prefix and delimited lower-case UTF-8 hex escapes.
    """

    stable = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_.")
    stem = part.split(".", 1)[0]
    reserved = {"con", "prn", "aux", "nul"} | {
        f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
    }
    if (
        all(character in stable for character in part)
        and not part.endswith((" ", "."))
        and stem not in reserved
    ):
        return part
    trailing_start = len(part.rstrip(" ."))
    encoded_parts = [
        (
            character
            if character in stable and not (index >= trailing_start and character in " .")
            else "~" + character.encode("utf-8").hex() + "~"
        )
        for index, character in enumerate(part)
    ]
    encoded = WINDOWS_PHYSICAL_PREFIX + "".join(encoded_parts)
    if len(encoded) > WINDOWS_MAX_COMPONENT_LENGTH:
        raise ValueError("Object key component is too long for the Windows RAW store")
    return encoded


def _legacy_windows_physical_part(part: str) -> str:
    """Return the pre-correction Windows mapping for read compatibility."""

    marker = WINDOWS_PHYSICAL_PREFIX
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

    def _legacy_object_paths(self, object_key: str) -> tuple[Path, ...]:
        parts = self._validated_parts(object_key)
        candidates = (
            self._bounded_path([_legacy_windows_physical_part(part) for part in parts]),
            self._bounded_path(parts),
        )
        return tuple(dict.fromkeys(candidates))

    @staticmethod
    def _validated_parts(object_key: str) -> list[str]:
        if not object_key or "\x00" in object_key:
            raise ValueError("Object key must be a non-empty relative path")
        if PurePosixPath(object_key).is_absolute() or PureWindowsPath(object_key).is_absolute():
            raise ValueError("Absolute object keys are not allowed")

        if "\\" in object_key:
            raise ValueError("Object keys must use canonical '/' separators")
        parts = object_key.split("/")
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
            for legacy_path in self._legacy_object_paths(object_key):
                if legacy_path != path and legacy_path.exists():
                    path = legacy_path
                    break
        return path.read_bytes()
