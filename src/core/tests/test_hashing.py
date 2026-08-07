from __future__ import annotations

from pathlib import Path

from core.hashing import sha256_file, sha256_hex


def test_sha256_is_deterministic():
    payload = b"deterministic-test-bytes"
    assert sha256_hex(payload) == sha256_hex(payload)


def test_sha256_file_matches_bytes(tmp_path: Path):
    file_path = tmp_path / "artifact.bin"
    payload = b"raw-content"
    file_path.write_bytes(payload)
    assert sha256_file(file_path) == sha256_hex(payload)
