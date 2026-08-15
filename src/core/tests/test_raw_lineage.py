from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from django.core.management import load_command_class

from core.models import RawArtifact
from core.raw_lineage import (
    SENTINEL_NAME,
    RawLineageError,
    SourceRoot,
    build_designation,
    canonical_datetime,
    capture_manifest,
    consolidate_manifest,
    fingerprint,
    validate_designated_operational_root,
    verify_manifest,
    write_json,
)
from core.storage import RawObjectStore


def _artifact(key: str, content: bytes, content_type: str = "application/json") -> RawArtifact:
    return RawArtifact.objects.create(
        object_key=key,
        sha256_digest=__import__("hashlib").sha256(content).hexdigest(),
        byte_size=len(content),
        content_type=content_type,
    )


def _pua_path(root: Path, key: str) -> Path:
    path = root.joinpath(*(part.replace(":", "\uf022") for part in key.split("/")))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _capture_fixture(root_a: Path, root_b: Path) -> tuple[dict[str, object], bytes, bytes]:
    first = b'{"first":1}'
    second = b'{"legacy":2}'
    first_key = "source/a/first.json"
    second_key = "source/b/detail:2.json"
    _artifact(first_key, first)
    _artifact(second_key, second)
    RawObjectStore(root_a).write_bytes(first_key, first)
    _pua_path(root_b, second_key).write_bytes(second)
    manifest = capture_manifest(
        (
            SourceRoot.create("historical_a", root_a),
            SourceRoot.create("historical_b", root_b),
        )
    )
    return manifest, first, second


def test_canonical_datetime_is_fixed_utc_and_rejects_naive() -> None:
    value = datetime(2026, 8, 15, 12, 30, 1, 2, tzinfo=UTC)
    assert canonical_datetime(value) == "2026-08-15T12:30:01.000002Z"
    with pytest.raises(RawLineageError, match="naive"):
        canonical_datetime(datetime(2026, 8, 15, 12, 30, 1))


@pytest.mark.django_db(transaction=True)
def test_manifest_reconciles_exact_u_f022_and_recomputes_every_hash() -> None:
    with TemporaryDirectory() as first_path, TemporaryDirectory() as second_path:
        manifest, _, _ = _capture_fixture(Path(first_path), Path(second_path))
    assert manifest["object_count"] == 2
    assert manifest["representation_counts"] == {
        "CURRENT_C3": 1,
        "LEGACY_U_F022_COLON": 1,
    }
    verify_manifest(manifest)
    tampered = json.loads(json.dumps(manifest))
    tampered["rows"][1]["byte_size"] += 1
    tampered["manifest_sha256"] = fingerprint(
        {key: value for key, value in tampered.items() if key != "manifest_sha256"}
    )
    with pytest.raises(RawLineageError, match="row fingerprint"):
        verify_manifest(tampered)


@pytest.mark.django_db(transaction=True)
def test_manifest_fails_before_accepting_ambiguous_source_identity() -> None:
    content = b"same"
    key = "source/same.json"
    _artifact(key, content)
    with TemporaryDirectory() as first_path, TemporaryDirectory() as second_path:
        first = Path(first_path)
        second = Path(second_path)
        RawObjectStore(first).write_bytes(key, content)
        RawObjectStore(second).write_bytes(key, content)
        with pytest.raises(RawLineageError, match="AMBIGUOUS"):
            capture_manifest(
                (SourceRoot.create("first", first), SourceRoot.create("second", second))
            )


@pytest.mark.django_db(transaction=True)
def test_manifest_fails_on_conflicting_source_bytes() -> None:
    expected = b"expected"
    key = "source/conflict.json"
    _artifact(key, expected)
    with TemporaryDirectory() as root_path:
        root = Path(root_path)
        RawObjectStore(root).write_bytes(key, b"different")
        with pytest.raises(RawLineageError, match="CONFLICTING"):
            capture_manifest((SourceRoot.create("source", root),))


@pytest.mark.django_db(transaction=True)
def test_dry_run_is_write_free_and_apply_replays_exactly() -> None:
    with (
        TemporaryDirectory() as first_path,
        TemporaryDirectory() as second_path,
        TemporaryDirectory() as destination_parent,
        TemporaryDirectory() as evidence_path,
    ):
        first = Path(first_path)
        second = Path(second_path)
        destination = Path(destination_parent) / "canonical"
        manifest, first_bytes, second_bytes = _capture_fixture(first, second)
        designation_path = Path(evidence_path) / "designation.json"
        write_json(designation_path, build_designation(manifest))
        roots = (
            SourceRoot.create("historical_a", first),
            SourceRoot.create("historical_b", second),
        )
        with patch("core.raw_lineage.DESIGNATION_PATH", designation_path):
            dry = consolidate_manifest(manifest, roots, destination, dry_run=True)
            assert dry.created == 0
            assert not destination.exists()

            first_result = consolidate_manifest(manifest, roots, destination, dry_run=False)
            sentinel_bytes = RawObjectStore(destination).read_bytes(SENTINEL_NAME)
            second_result = consolidate_manifest(manifest, roots, destination, dry_run=False)

        store = RawObjectStore(destination)
        assert store.read_bytes("source/a/first.json") == first_bytes
        assert store.read_bytes("source/b/detail:2.json") == second_bytes
        assert first_result.created == 2
        assert first_result.sentinel_created
        assert second_result.created == 0
        assert second_result.reused == 2
        assert second_result.sentinel_reused
        assert store.read_bytes(SENTINEL_NAME) == sentinel_bytes


@pytest.mark.django_db(transaction=True)
def test_destination_conflict_stops_before_other_publication() -> None:
    with (
        TemporaryDirectory() as first_path,
        TemporaryDirectory() as second_path,
        TemporaryDirectory() as destination_path,
        TemporaryDirectory() as evidence_path,
    ):
        first = Path(first_path)
        second = Path(second_path)
        destination = Path(destination_path)
        manifest, _, _ = _capture_fixture(first, second)
        designation_path = Path(evidence_path) / "designation.json"
        write_json(designation_path, build_designation(manifest))
        store = RawObjectStore(destination)
        store.write_bytes("source/b/detail:2.json", b"conflicting")
        roots = (
            SourceRoot.create("historical_a", first),
            SourceRoot.create("historical_b", second),
        )
        with (
            patch("core.raw_lineage.DESIGNATION_PATH", designation_path),
            pytest.raises(RawLineageError, match="destination bytes conflict"),
        ):
            consolidate_manifest(manifest, roots, destination, dry_run=False)
        assert not store.object_path("source/a/first.json").exists()
        assert store.read_bytes("source/b/detail:2.json") == b"conflicting"
        with pytest.raises(FileNotFoundError):
            store.read_bytes(SENTINEL_NAME)


@pytest.mark.django_db(transaction=True)
def test_database_drift_stops_before_destination_creation() -> None:
    with (
        TemporaryDirectory() as first_path,
        TemporaryDirectory() as second_path,
        TemporaryDirectory() as destination_parent,
        TemporaryDirectory() as evidence_path,
    ):
        first = Path(first_path)
        second = Path(second_path)
        destination = Path(destination_parent) / "canonical"
        manifest, _, _ = _capture_fixture(first, second)
        designation_path = Path(evidence_path) / "designation.json"
        write_json(designation_path, build_designation(manifest))
        _artifact("later/new.json", b"later")
        roots = (
            SourceRoot.create("historical_a", first),
            SourceRoot.create("historical_b", second),
        )
        with (
            patch("core.raw_lineage.DESIGNATION_PATH", designation_path),
            pytest.raises(RawLineageError, match="current database"),
        ):
            consolidate_manifest(manifest, roots, destination, dry_run=False)
        assert not destination.exists()


@pytest.mark.django_db(transaction=True)
def test_runtime_source_root_must_match_audited_identity() -> None:
    with (
        TemporaryDirectory() as first_path,
        TemporaryDirectory() as second_path,
        TemporaryDirectory() as replacement_path,
        TemporaryDirectory() as destination_parent,
        TemporaryDirectory() as evidence_path,
    ):
        first = Path(first_path)
        second = Path(second_path)
        manifest, _, _ = _capture_fixture(first, second)
        designation_path = Path(evidence_path) / "designation.json"
        write_json(designation_path, build_designation(manifest))
        replacement = Path(replacement_path)
        roots = (
            SourceRoot.create("historical_a", replacement),
            SourceRoot.create("historical_b", second),
        )
        with (
            patch("core.raw_lineage.DESIGNATION_PATH", designation_path),
            pytest.raises(RawLineageError, match="runtime source roots"),
        ):
            consolidate_manifest(
                manifest,
                roots,
                Path(destination_parent) / "canonical",
                dry_run=True,
            )


@pytest.mark.django_db(transaction=True)
def test_designated_root_validation_rejects_missing_or_wrong_manifest() -> None:
    with TemporaryDirectory() as root_path, TemporaryDirectory() as evidence_path:
        root = Path(root_path)
        designation = {
            "designation_version": "operational-raw-lineage-designation-v0.1",
            "lineage_version": "operational-raw-lineage-v0.1",
            "manifest_sha256": "a" * 64,
        }
        designation_path = Path(evidence_path) / "designation.json"
        write_json(designation_path, designation)
        with (
            patch("core.raw_lineage.DESIGNATION_PATH", designation_path),
            pytest.raises(RawLineageError, match="sentinel is missing"),
        ):
            validate_designated_operational_root(root, "a" * 64)
        RawObjectStore(root).write_bytes(
            SENTINEL_NAME,
            json.dumps({**designation, "replicated_at": "2026-08-15T00:00:00.000000Z"}).encode(),
        )
        with patch("core.raw_lineage.DESIGNATION_PATH", designation_path):
            assert (
                validate_designated_operational_root(root, "a" * 64)["manifest_sha256"] == "a" * 64
            )
            with pytest.raises(RawLineageError, match="configured RAW manifest"):
                validate_designated_operational_root(root, "b" * 64)


def test_production_command_has_no_designation_override() -> None:
    command = load_command_class("core", "consolidate_operational_raw_lineage")
    parser = command.create_parser("manage.py", "consolidate_operational_raw_lineage")
    assert "--designation" not in parser.format_help()
