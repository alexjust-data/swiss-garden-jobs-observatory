from __future__ import annotations

from pathlib import Path

import pytest

from core.hashing import sha256_file, sha256_hex
from core.storage import RawObjectAlreadyExistsError, RawObjectStore


def test_raw_object_store_is_strictly_write_once(tmp_path: Path) -> None:
    store = RawObjectStore(tmp_path / "raw")
    object_key = "winterthur/run/detail.html"
    original = b"original exact bytes"
    original_digest = sha256_hex(original)

    path = store.write_bytes(object_key, original)
    assert store.read_bytes(object_key) == original
    assert sha256_file(path) == original_digest

    with pytest.raises(RawObjectAlreadyExistsError, match="already exists"):
        store.write_bytes(object_key, original)
    assert store.read_bytes(object_key) == original
    assert sha256_file(path) == original_digest

    with pytest.raises(RawObjectAlreadyExistsError, match="already exists"):
        store.write_bytes(object_key, b"different bytes")
    assert store.read_bytes(object_key) == original
    assert sha256_file(path) == original_digest
