"""Deterministic hash helpers for raw objects."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    chunk_size = 8192
    target = Path(path)

    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)

    return digest.hexdigest()
