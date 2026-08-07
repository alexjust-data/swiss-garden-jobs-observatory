from __future__ import annotations

from pathlib import Path

import pytest

from core.storage import RawObjectStore


def test_raw_store_roundtrip(tmp_path: Path) -> None:
    store = RawObjectStore(base_path=tmp_path / "raw")
    payload = b"raw-object-content"
    object_key = "hello.bin"

    path = store.write_bytes(object_key, payload)
    assert path.exists()
    assert path.read_bytes() == payload
    assert store.read_bytes(object_key) == payload


def test_raw_store_supports_valid_subdirectories(tmp_path: Path) -> None:
    store = RawObjectStore(base_path=tmp_path / "raw")

    path = store.write_bytes("source/2026/observation.html", b"content")

    assert path == (tmp_path / "raw" / "source" / "2026" / "observation.html").resolve()
    assert store.read_bytes("source/2026/observation.html") == b"content"


@pytest.mark.parametrize(
    "object_key",
    [
        "../foo",
        "../../foo",
        "a/../../../foo",
        "a/../foo",
    ],
)
def test_raw_store_rejects_parent_segments(tmp_path: Path, object_key: str) -> None:
    store = RawObjectStore(base_path=tmp_path / "raw")

    with pytest.raises(ValueError):
        store.write_bytes(object_key, b"unsafe")
    with pytest.raises(ValueError):
        store.read_bytes(object_key)


@pytest.mark.parametrize("object_key", ["/foo", "//foo", "C:\\foo", "\\\\server\\share"])
def test_raw_store_rejects_absolute_paths(tmp_path: Path, object_key: str) -> None:
    store = RawObjectStore(base_path=tmp_path / "raw")

    with pytest.raises(ValueError):
        store.write_bytes(object_key, b"unsafe")
    with pytest.raises(ValueError):
        store.read_bytes(object_key)


def test_raw_store_cannot_access_files_outside_base_path(tmp_path: Path) -> None:
    store = RawObjectStore(base_path=tmp_path / "raw")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"sentinel")

    with pytest.raises(ValueError):
        store.write_bytes("../outside.bin", b"overwritten")
    with pytest.raises(ValueError):
        store.read_bytes("../outside.bin")

    assert outside.read_bytes() == b"sentinel"
