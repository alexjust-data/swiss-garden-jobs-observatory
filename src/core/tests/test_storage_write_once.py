from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core.hashing import sha256_file, sha256_hex
from core.storage import RawObjectAlreadyExistsError, RawObjectStore


def test_raw_object_store_reuses_only_identical_bytes(tmp_path: Path) -> None:
    store = RawObjectStore(tmp_path / "raw")
    object_key = "winterthur/run/detail.html"
    original = b"original exact bytes"
    original_digest = sha256_hex(original)

    path = store.write_bytes(object_key, original)
    assert store.read_bytes(object_key) == original
    assert sha256_file(path) == original_digest
    assert store.write_bytes(object_key, original) == path
    assert store.read_bytes(object_key) == original
    assert sha256_file(path) == original_digest

    with pytest.raises(RawObjectAlreadyExistsError, match="conflicting bytes"):
        store.write_bytes(object_key, b"different bytes")
    assert store.read_bytes(object_key) == original
    assert sha256_file(path) == original_digest


def test_concurrent_identical_raw_publication_converges_atomically(tmp_path: Path) -> None:
    store = RawObjectStore(tmp_path / "raw")
    object_key = "geocoder/provider/request-response.json"
    content = b'{"complete":"payload"}' * 4096

    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda _: store.write_bytes(object_key, content), range(24)))

    assert set(paths) == {store.object_path(object_key)}
    assert store.read_bytes(object_key) == content
    assert sha256_file(paths[0]) == sha256_hex(content)
    assert list(paths[0].parent.glob(".raw-*.tmp")) == []


def test_concurrent_conflicting_raw_publication_never_overwrites(
    tmp_path: Path,
) -> None:
    store = RawObjectStore(tmp_path / "raw")
    object_key = "geocoder/provider/conflict.json"
    first = b"A" * 65536
    second = b"B" * 65536

    def publish(content: bytes) -> Path | RawObjectAlreadyExistsError:
        try:
            return store.write_bytes(object_key, content)
        except RawObjectAlreadyExistsError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(publish, (first, second)))

    stored = store.read_bytes(object_key)
    assert stored in (first, second)
    assert sum(isinstance(item, RawObjectAlreadyExistsError) for item in results) == 1
    assert list(store.object_path(object_key).parent.glob(".raw-*.tmp")) == []


def test_content_addressed_long_key_uses_short_same_directory_temporary(
    tmp_path: Path,
) -> None:
    store = RawObjectStore(tmp_path / "raw")
    request_fingerprint = "b0c9b6ea8808f4eee7835d146ec982145ede6e3db524e8207e20b7880094c491"
    object_key = (
        "geocoder/swisstopo_searchserver/geo-admin-searchserver-api-2026-08/"
        f"{request_fingerprint}-170fb4196ca4a485.json"
    )
    content = b'{"complete":"content-addressed-response"}'

    path = store.write_bytes(object_key, content)

    assert path.is_file()
    assert store.write_bytes(object_key, content) == path
    assert store.read_bytes(object_key) == content
    assert list(path.parent.glob(".raw-*.tmp")) == []


def test_windows_forbidden_characters_have_collision_free_physical_names(
    tmp_path: Path,
) -> None:
    store = RawObjectStore(tmp_path / "raw")
    colon_key = "sources/source/detail-court:70001-hash"
    percent_key = "sources/source/detail-court%3A70001-hash"

    colon_path = store.write_bytes(colon_key, b"colon")
    percent_path = store.write_bytes(percent_key, b"percent")

    assert colon_path != percent_path
    assert store.read_bytes(colon_key) == b"colon"
    assert store.read_bytes(percent_key) == b"percent"
    if os.name == "nt":
        assert colon_path.name == "~raw~detail-court%3A70001-hash"
        assert percent_path.name == "detail-court%3A70001-hash"
