from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core.hashing import sha256_file, sha256_hex
from core.storage import (
    RawObjectAlreadyExistsError,
    RawObjectStore,
    _encode_windows_physical_part,
)


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
    assert _encode_windows_physical_part("detail-court:70001-hash").casefold() != (
        _encode_windows_physical_part("detail-court%3A70001-hash").casefold()
    )
    if os.name == "nt":
        assert colon_path.name == _encode_windows_physical_part("detail-court:70001-hash")
        assert percent_path.name == _encode_windows_physical_part("detail-court%3A70001-hash")


@pytest.mark.parametrize(
    ("left", "right"),
    (
        ("Foo", "foo"),
        ("CON", "con"),
        ("A:B", "a:b"),
        ("A:B", "A%3AB"),
        ("name.", "name"),
        ("name ", "name"),
        ("~raw~literal", "literal"),
        ("Ä", "ä"),
    ),
)
def test_windows_physical_components_are_injective_after_case_folding(
    tmp_path: Path,
    left: str,
    right: str,
) -> None:
    left_physical = _encode_windows_physical_part(left)
    right_physical = _encode_windows_physical_part(right)

    assert left_physical.casefold() != right_physical.casefold()
    assert not left_physical.endswith((" ", "."))
    assert not right_physical.endswith((" ", "."))

    store = RawObjectStore(tmp_path / "raw")
    left_key = f"identity/{left}"
    right_key = f"identity/{right}"
    left_path = store.write_bytes(left_key, b"left")
    right_path = store.write_bytes(right_key, b"right")
    assert left_path != right_path
    assert store.read_bytes(left_key) == b"left"
    assert store.read_bytes(right_key) == b"right"


def test_backslash_is_not_a_second_logical_separator(tmp_path: Path) -> None:
    store = RawObjectStore(tmp_path / "raw")

    with pytest.raises(ValueError, match="canonical '/' separators"):
        store.object_path(r"identity\child")


@pytest.fixture
def windows_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(RawObjectStore, "_uses_windows_layout", staticmethod(lambda: True))


def test_windows_legacy_physical_object_remains_readable(
    tmp_path: Path,
    windows_layout: None,
) -> None:
    store = RawObjectStore(tmp_path / "raw")
    object_key = "legacy/detail:1.json"
    legacy_path = store._legacy_object_paths(object_key)[0]
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(b"legacy")

    assert not store.object_path(object_key).exists()
    assert store.read_bytes(object_key) == b"legacy"


@pytest.mark.parametrize("content", (b"legacy", b"different"))
def test_windows_write_reconciles_exact_legacy_identity_before_publication(
    tmp_path: Path,
    windows_layout: None,
    content: bytes,
) -> None:
    store = RawObjectStore(tmp_path / "raw")
    object_key = "legacy/detail:1.json"
    legacy_path = store._legacy_object_paths(object_key)[0]
    new_path = store.object_path(object_key)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(b"legacy")

    if content == b"legacy":
        assert store.write_bytes(object_key, content) == legacy_path
    else:
        with pytest.raises(RawObjectAlreadyExistsError, match="conflicting bytes"):
            store.write_bytes(object_key, content)

    assert legacy_path.read_bytes() == b"legacy"
    assert not new_path.exists()


def test_windows_legacy_case_alias_cannot_claim_another_logical_key(
    tmp_path: Path,
    windows_layout: None,
) -> None:
    store = RawObjectStore(tmp_path / "raw")
    lower_path = store._legacy_object_paths("legacy/foo")[0]
    upper_new_path = store.object_path("legacy/Foo")
    lower_path.parent.mkdir(parents=True, exist_ok=True)
    lower_path.write_bytes(b"lower")

    with pytest.raises(FileNotFoundError):
        store.read_bytes("legacy/Foo")

    assert store.write_bytes("legacy/Foo", b"upper") == upper_new_path
    assert store.read_bytes("legacy/foo") == b"lower"
    assert store.read_bytes("legacy/Foo") == b"upper"


def test_windows_conflicting_dual_layout_fails_closed(
    tmp_path: Path,
    windows_layout: None,
) -> None:
    store = RawObjectStore(tmp_path / "raw")
    object_key = "legacy/detail:1.json"
    legacy_path = store._legacy_object_paths(object_key)[0]
    new_path = store.object_path(object_key)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(b"legacy")
    new_path.write_bytes(b"shadow")

    with pytest.raises(RawObjectAlreadyExistsError, match="conflicting bytes"):
        store.read_bytes(object_key)
    with pytest.raises(RawObjectAlreadyExistsError, match="conflicting bytes"):
        store.write_bytes(object_key, b"shadow")


def test_windows_legacy_uppercase_alias_blocks_lowercase_new_identity(
    tmp_path: Path,
    windows_layout: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RawObjectStore(tmp_path / "raw")
    upper_legacy_path = store._legacy_object_paths("legacy/Foo")[0]
    lower_new_path = store.object_path("legacy/foo")
    upper_legacy_path.parent.mkdir(parents=True, exist_ok=True)
    upper_legacy_path.write_bytes(b"same")

    def refuse_casefolded_alias(_source: str | Path, destination: str | Path) -> None:
        raise FileExistsError(destination)

    monkeypatch.setattr("core.storage.os.rename", refuse_casefolded_alias)
    with pytest.raises(FileNotFoundError):
        store.read_bytes("legacy/foo")
    with pytest.raises(RawObjectAlreadyExistsError, match="another logical key"):
        store.write_bytes("legacy/foo", b"same")

    assert upper_legacy_path.read_bytes() == b"same"
    assert not store._exact_existing_path(lower_new_path)
