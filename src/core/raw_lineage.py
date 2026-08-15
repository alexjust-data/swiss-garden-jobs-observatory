"""Governed operational RAW lineage capture, consolidation, and validation."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from core.models import RawArtifact
from core.storage import (
    RawObjectAlreadyExistsError,
    RawObjectStore,
    _encode_windows_physical_part,
    _legacy_windows_physical_part,
)

LINEAGE_VERSION = "operational-raw-lineage-v0.1"
MANIFEST_VERSION = "operational-raw-lineage-manifest-v0.1"
DESIGNATION_VERSION = "operational-raw-lineage-designation-v0.1"
SENTINEL_NAME = ".operational-raw-lineage-v0.1.json"
BASELINE_SHA = "0a6dc823b4716cbaea1cf5f3418881ed79410d33"
CONTRACT_COMMIT = "2f092daf77c8e5131226fcd793a77ca9d6d38212"
DESIGNATION_PATH = (
    Path(settings.BASE_DIR)
    / "docs"
    / "day0"
    / "gate_010_c4_operational_raw_lineage_designation_v0_1.json"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class RawLineageError(RuntimeError):
    """Fail-closed C4 lineage error."""


@dataclass(frozen=True)
class SourceRoot:
    label: str
    path: Path

    @classmethod
    def create(cls, label: str, path: str | Path) -> SourceRoot:
        if not _LABEL_RE.fullmatch(label):
            raise RawLineageError(f"invalid source-root label: {label}")
        candidate = Path(path)
        if not candidate.is_absolute():
            raise RawLineageError(f"source root must be absolute: {label}")
        resolved = candidate.resolve()
        if not resolved.is_dir():
            raise RawLineageError(f"source root does not exist: {label}")
        return cls(label=label, path=resolved)


@dataclass(frozen=True)
class ConsolidationResult:
    lineage_version: str
    manifest_sha256: str
    selected: int
    created: int
    reused: int
    dry_run: bool
    sentinel_created: bool
    sentinel_reused: bool
    aggregate_byte_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RawLineageError("naive datetime is not canonical lineage evidence")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fingerprint(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RawLineageError(f"cannot load governed JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RawLineageError(f"governed JSON must be an object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def parse_source_roots(values: Iterable[str]) -> tuple[SourceRoot, ...]:
    roots: list[SourceRoot] = []
    for value in values:
        label, separator, raw_path = value.partition("=")
        if not separator or not raw_path:
            raise RawLineageError("source roots must use LABEL=ABSOLUTE_PATH")
        roots.append(SourceRoot.create(label, raw_path))
    if not roots:
        raise RawLineageError("at least one source root is required")
    labels = [root.label for root in roots]
    identities = [_path_identity(root.path) for root in roots]
    if len(labels) != len(set(labels)):
        raise RawLineageError("source-root labels must be unique")
    if len(identities) != len(set(identities)):
        raise RawLineageError("source roots must be physically distinct")
    return tuple(sorted(roots, key=lambda item: item.label))


def _path_identity(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _path_identity_sha256(path: Path) -> str:
    return sha256_bytes(_path_identity(path).encode("utf-8"))


def _relative_posix(path: Path, root: Path) -> str:
    return "/".join(path.relative_to(root).parts)


def _source_inventories(roots: tuple[SourceRoot, ...]) -> dict[str, set[str]]:
    inventories: dict[str, set[str]] = {}
    for root in roots:
        files: set[str] = set()
        for directory_path, directory_names, filenames in os.walk(root.path):
            directory = Path(directory_path)
            for directory_name in directory_names:
                candidate = directory / directory_name
                if candidate.is_symlink():
                    raise RawLineageError(f"source root contains symlink: {root.label}")
            for filename in filenames:
                candidate = directory / filename
                if candidate.is_symlink():
                    raise RawLineageError(f"source root contains symlink: {root.label}")
                files.add(_relative_posix(candidate, root.path))
        inventories[root.label] = files
    return inventories


def _candidate_relative_paths(object_key: str) -> dict[str, str]:
    parts = RawObjectStore._validated_parts(object_key)
    current_parts = (
        [_encode_windows_physical_part(part) for part in parts] if os.name == "nt" else parts
    )
    candidates: list[tuple[str, list[str]]] = [("CURRENT_C3", current_parts)]
    candidates.append(("LEGACY_C3", [_legacy_windows_physical_part(part) for part in parts]))
    if ":" in object_key:
        candidates.append(("LEGACY_U_F022_COLON", [part.replace(":", "\uf022") for part in parts]))

    physical: dict[str, str] = {}
    seen_paths: set[str] = set()
    for representation, physical_parts in candidates:
        relative = "/".join(physical_parts)
        if relative in seen_paths:
            continue
        seen_paths.add(relative)
        physical[representation] = relative
    return physical


def _locate_source(
    object_key: str,
    roots: tuple[SourceRoot, ...],
    inventories: Mapping[str, set[str]],
) -> tuple[str, str, Path]:
    matches: list[tuple[str, str, Path]] = []
    for root in roots:
        for representation, relative in _candidate_relative_paths(object_key).items():
            if relative in inventories[root.label]:
                matches.append(
                    (root.label, representation, root.path.joinpath(*relative.split("/")))
                )
    if not matches:
        raise RawLineageError(f"MISSING RAW identity: {object_key}")
    physical = {
        (label, str(path)): (label, representation, path) for label, representation, path in matches
    }
    if len(physical) != 1:
        raise RawLineageError(f"AMBIGUOUS RAW identity: {object_key}")
    return next(iter(physical.values()))


def _migration_inventory() -> list[dict[str, str]]:
    return [
        {"app": app, "name": name}
        for app, name in MigrationRecorder.Migration.objects.order_by("app", "name").values_list(
            "app", "name"
        )
    ]


def _snapshot_metadata() -> dict[str, object]:
    database_name = str(connection.settings_dict.get("NAME", ""))
    host = str(connection.settings_dict.get("HOST", ""))
    port = str(connection.settings_dict.get("PORT", ""))
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT txid_current_snapshot(), transaction_timestamp()")
            transaction_snapshot, started_at = cursor.fetchone()
    else:
        transaction_snapshot = f"unavailable:{connection.vendor}"
        started_at = timezone.now()
    return {
        "database_name": database_name,
        "vendor": connection.vendor,
        "server_identity_sha256": fingerprint(
            {"vendor": connection.vendor, "host": host, "port": port}
        ),
        "transaction_snapshot": str(transaction_snapshot),
        "transaction_started_at": canonical_datetime(started_at),
        "migrations": _migration_inventory(),
        "merged_baseline_sha": BASELINE_SHA,
    }


def _raw_authority_payload(row: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": int(row["id"]),
        "object_key": str(row["object_key"]),
        "sha256_digest": str(row["sha256_digest"]),
        "byte_size": int(row["byte_size"]),
        "content_type": str(row["content_type"]),
    }


def _integer(value: object) -> int:
    if not isinstance(value, int):
        raise RawLineageError("lineage integer field has an invalid type")
    return value


def _manifest_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "manifest_sha256"}


def capture_manifest(roots: tuple[SourceRoot, ...]) -> dict[str, Any]:
    """Capture one coherent read-only database/source inventory."""

    inventories = _source_inventories(roots)
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot = _snapshot_metadata()
        authority_rows = sorted(
            RawArtifact.objects.values(
                "id", "object_key", "sha256_digest", "byte_size", "content_type"
            ),
            key=lambda row: str(row["object_key"]),
        )
        rows: list[dict[str, object]] = []
        representation_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {root.label: 0 for root in roots}
        aggregate_byte_count = 0
        for authority_row in authority_rows:
            authority = _raw_authority_payload(authority_row)
            label, representation, physical_path = _locate_source(
                str(authority["object_key"]), roots, inventories
            )
            raw = physical_path.read_bytes()
            actual_sha = sha256_bytes(raw)
            if len(raw) != authority["byte_size"] or actual_sha != authority["sha256_digest"]:
                raise RawLineageError(f"CONFLICTING RAW identity: {authority['object_key']}")
            row: dict[str, object] = {
                **authority,
                "source_label": label,
                "representation": representation,
                "source_relative_path": _relative_posix(
                    physical_path, next(root.path for root in roots if root.label == label)
                ),
            }
            row["row_sha256"] = fingerprint(row)
            rows.append(row)
            source_counts[label] += 1
            representation_counts[representation] = representation_counts.get(representation, 0) + 1
            aggregate_byte_count += _integer(authority["byte_size"])

    raw_inventory_fingerprint = fingerprint([_raw_authority_payload(row) for row in rows])
    source_inventory_fingerprint = fingerprint([row["row_sha256"] for row in rows])
    source_roots = [
        {
            "label": root.label,
            "root_identity_sha256": _path_identity_sha256(root.path),
            "referenced_object_count": source_counts[root.label],
        }
        for root in roots
    ]
    database_snapshot_fingerprint = fingerprint(
        {
            "snapshot_metadata": snapshot,
            "raw_inventory_fingerprint": raw_inventory_fingerprint,
            "source_inventory_fingerprint": source_inventory_fingerprint,
            "object_count": len(rows),
            "aggregate_byte_count": aggregate_byte_count,
            "source_roots": source_roots,
            "representation_counts": dict(sorted(representation_counts.items())),
        }
    )
    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "lineage_version": LINEAGE_VERSION,
        "snapshot_metadata": snapshot,
        "database_snapshot_fingerprint": database_snapshot_fingerprint,
        "raw_inventory_fingerprint": raw_inventory_fingerprint,
        "source_inventory_fingerprint": source_inventory_fingerprint,
        "object_count": len(rows),
        "aggregate_byte_count": aggregate_byte_count,
        "source_roots": source_roots,
        "representation_counts": dict(sorted(representation_counts.items())),
        "rows": rows,
    }
    manifest["manifest_sha256"] = fingerprint(manifest)
    verify_manifest(manifest)
    return manifest


def verify_manifest(manifest: Mapping[str, Any]) -> None:
    expected_keys = {
        "manifest_version",
        "lineage_version",
        "snapshot_metadata",
        "database_snapshot_fingerprint",
        "raw_inventory_fingerprint",
        "source_inventory_fingerprint",
        "object_count",
        "aggregate_byte_count",
        "source_roots",
        "representation_counts",
        "rows",
        "manifest_sha256",
    }
    if set(manifest) != expected_keys:
        raise RawLineageError("manifest fields do not match the frozen format")
    if (
        manifest["manifest_version"] != MANIFEST_VERSION
        or manifest["lineage_version"] != LINEAGE_VERSION
    ):
        raise RawLineageError("unsupported RAW lineage manifest version")
    rows = manifest["rows"]
    if not isinstance(rows, list):
        raise RawLineageError("manifest rows must be an array")
    previous_key = ""
    authority_rows: list[dict[str, object]] = []
    row_hashes: list[str] = []
    source_counts: dict[str, int] = {}
    representation_counts: dict[str, int] = {}
    aggregate = 0
    for row_value in rows:
        if not isinstance(row_value, dict):
            raise RawLineageError("manifest row must be an object")
        row = dict(row_value)
        row_hash = str(row.pop("row_sha256", ""))
        if not _SHA256_RE.fullmatch(row_hash) or fingerprint(row) != row_hash:
            raise RawLineageError("manifest row fingerprint mismatch")
        authority = _raw_authority_payload(row)
        if not _SHA256_RE.fullmatch(str(authority["sha256_digest"])):
            raise RawLineageError("invalid RawArtifact SHA-256")
        key = str(authority["object_key"])
        if key <= previous_key:
            raise RawLineageError("manifest rows are not uniquely sorted by object key")
        previous_key = key
        authority_rows.append(authority)
        row_hashes.append(row_hash)
        aggregate += _integer(authority["byte_size"])
        label = str(row.get("source_label", ""))
        representation = str(row.get("representation", ""))
        source_counts[label] = source_counts.get(label, 0) + 1
        representation_counts[representation] = representation_counts.get(representation, 0) + 1

    if int(manifest["object_count"]) != len(rows):
        raise RawLineageError("manifest object count mismatch")
    if int(manifest["aggregate_byte_count"]) != aggregate:
        raise RawLineageError("manifest aggregate byte count mismatch")
    if manifest["raw_inventory_fingerprint"] != fingerprint(authority_rows):
        raise RawLineageError("manifest RawArtifact inventory mismatch")
    if manifest["source_inventory_fingerprint"] != fingerprint(row_hashes):
        raise RawLineageError("manifest source inventory mismatch")
    if manifest["representation_counts"] != dict(sorted(representation_counts.items())):
        raise RawLineageError("manifest representation counts mismatch")
    roots = manifest["source_roots"]
    if not isinstance(roots, list):
        raise RawLineageError("manifest source roots must be an array")
    declared_counts = {
        str(item["label"]): int(item["referenced_object_count"])
        for item in roots
        if isinstance(item, dict)
    }
    if declared_counts != source_counts:
        raise RawLineageError("manifest source-root counts mismatch")
    expected_snapshot = fingerprint(
        {
            "snapshot_metadata": manifest["snapshot_metadata"],
            "raw_inventory_fingerprint": manifest["raw_inventory_fingerprint"],
            "source_inventory_fingerprint": manifest["source_inventory_fingerprint"],
            "object_count": manifest["object_count"],
            "aggregate_byte_count": manifest["aggregate_byte_count"],
            "source_roots": roots,
            "representation_counts": manifest["representation_counts"],
        }
    )
    if manifest["database_snapshot_fingerprint"] != expected_snapshot:
        raise RawLineageError("database snapshot fingerprint mismatch")
    if manifest["manifest_sha256"] != fingerprint(_manifest_payload(manifest)):
        raise RawLineageError("manifest SHA-256 mismatch")


def build_designation(manifest: Mapping[str, Any]) -> dict[str, Any]:
    verify_manifest(manifest)
    return {
        "designation_version": DESIGNATION_VERSION,
        "lineage_version": LINEAGE_VERSION,
        "manifest_sha256": manifest["manifest_sha256"],
        "database_snapshot_fingerprint": manifest["database_snapshot_fingerprint"],
        "raw_inventory_fingerprint": manifest["raw_inventory_fingerprint"],
        "source_inventory_fingerprint": manifest["source_inventory_fingerprint"],
        "expected_object_count": manifest["object_count"],
        "expected_aggregate_byte_count": manifest["aggregate_byte_count"],
        "merged_baseline_sha": BASELINE_SHA,
        "contract_commit": CONTRACT_COMMIT,
    }


def verify_designation(manifest: Mapping[str, Any], designation: Mapping[str, Any]) -> None:
    expected = build_designation(manifest)
    if dict(designation) != expected:
        raise RawLineageError("manifest does not match the committed RAW lineage designation")


def _verify_current_database(manifest: Mapping[str, Any]) -> None:
    rows = [
        _raw_authority_payload(row)
        for row in sorted(
            RawArtifact.objects.values(
                "id", "object_key", "sha256_digest", "byte_size", "content_type"
            ),
            key=lambda row: str(row["object_key"]),
        )
    ]
    if fingerprint(rows) != manifest["raw_inventory_fingerprint"]:
        raise RawLineageError(
            "current database RawArtifact inventory differs from audited manifest"
        )


def _root_is_inside_git_worktree(path: Path) -> bool:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return True
    return False


def _verify_runtime_roots(
    manifest: Mapping[str, Any], roots: tuple[SourceRoot, ...], destination: Path
) -> None:
    if not destination.is_absolute():
        raise RawLineageError("destination RAW root must be absolute")
    destination_identity = _path_identity(destination)
    if destination_identity in {_path_identity(root.path) for root in roots}:
        raise RawLineageError("destination RAW root must differ from every source root")
    if _root_is_inside_git_worktree(destination):
        raise RawLineageError("destination RAW root must be outside every Git worktree")
    declared = {
        str(item["label"]): str(item["root_identity_sha256"]) for item in manifest["source_roots"]
    }
    actual = {root.label: _path_identity_sha256(root.path) for root in roots}
    if actual != declared:
        raise RawLineageError("runtime source roots differ from audited manifest")


def _verified_manifest_sources(
    manifest: Mapping[str, Any], roots: tuple[SourceRoot, ...]
) -> dict[str, Path]:
    root_map = {root.label: root for root in roots}
    inventories = _source_inventories(roots)
    verified: dict[str, Path] = {}
    for row in manifest["rows"]:
        object_key = str(row["object_key"])
        label = str(row["source_label"])
        if label not in root_map:
            raise RawLineageError(f"manifest source label is unavailable: {label}")
        located_label, representation, path = _locate_source(object_key, roots, inventories)
        if located_label != label or representation != row["representation"]:
            raise RawLineageError(f"source identity changed since manifest: {object_key}")
        if _relative_posix(path, root_map[label].path) != row["source_relative_path"]:
            raise RawLineageError(f"source path changed since manifest: {object_key}")
        raw = path.read_bytes()
        if len(raw) != row["byte_size"] or sha256_bytes(raw) != row["sha256_digest"]:
            raise RawLineageError(f"source bytes changed since manifest: {object_key}")
        verified[object_key] = path
    return verified


def _sentinel_payload(designation: Mapping[str, Any], replicated_at: datetime) -> dict[str, Any]:
    return {
        **dict(designation),
        "replicated_at": canonical_datetime(replicated_at),
    }


def _verify_sentinel(
    raw: bytes, designation: Mapping[str, Any], expected_manifest_sha256: str | None = None
) -> dict[str, Any]:
    try:
        sentinel = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RawLineageError("operational RAW lineage sentinel is malformed") from exc
    if not isinstance(sentinel, dict):
        raise RawLineageError("operational RAW lineage sentinel must be an object")
    for key, value in designation.items():
        if sentinel.get(key) != value:
            raise RawLineageError("operational RAW lineage sentinel conflicts with designation")
    if expected_manifest_sha256 and sentinel.get("manifest_sha256") != expected_manifest_sha256:
        raise RawLineageError("operational RAW lineage sentinel has an unexpected manifest")
    replicated_at = sentinel.get("replicated_at")
    if not isinstance(replicated_at, str) or not replicated_at.endswith("Z"):
        raise RawLineageError("operational RAW lineage sentinel has invalid replication time")
    return sentinel


def consolidate_manifest(
    manifest: Mapping[str, Any],
    roots: tuple[SourceRoot, ...],
    destination: Path,
    *,
    dry_run: bool,
) -> ConsolidationResult:
    """Authoritative mutation path pinned to the repository designation."""

    designation = load_json(DESIGNATION_PATH)
    verify_manifest(manifest)
    verify_designation(manifest, designation)
    _verify_current_database(manifest)
    destination = destination.resolve()
    _verify_runtime_roots(manifest, roots, destination)
    sources = _verified_manifest_sources(manifest, roots)

    destination_store = RawObjectStore(destination) if destination.exists() else None
    existing: set[str] = set()
    sentinel_reused = False
    if destination_store is not None:
        try:
            sentinel_raw = destination_store.read_bytes(SENTINEL_NAME)
        except FileNotFoundError:
            sentinel_raw = None
        if sentinel_raw is not None:
            _verify_sentinel(sentinel_raw, designation)
            sentinel_reused = True
        for row in manifest["rows"]:
            object_key = str(row["object_key"])
            try:
                raw = destination_store.read_bytes(object_key)
            except FileNotFoundError:
                continue
            except (RawObjectAlreadyExistsError, ValueError) as exc:
                raise RawLineageError(f"destination ownership conflict: {object_key}") from exc
            if len(raw) != row["byte_size"] or sha256_bytes(raw) != row["sha256_digest"]:
                raise RawLineageError(f"destination bytes conflict: {object_key}")
            existing.add(object_key)

    if sentinel_reused and len(existing) != int(manifest["object_count"]):
        raise RawLineageError("designated operational RAW root is incomplete")

    if dry_run:
        return ConsolidationResult(
            lineage_version=LINEAGE_VERSION,
            manifest_sha256=str(manifest["manifest_sha256"]),
            selected=int(manifest["object_count"]),
            created=0,
            reused=len(existing),
            dry_run=True,
            sentinel_created=False,
            sentinel_reused=sentinel_reused,
            aggregate_byte_count=int(manifest["aggregate_byte_count"]),
        )

    destination.mkdir(parents=True, exist_ok=True)
    destination_store = RawObjectStore(destination)
    created = 0
    for row in manifest["rows"]:
        object_key = str(row["object_key"])
        if object_key in existing:
            continue
        raw = sources[object_key].read_bytes()
        try:
            destination_store.write_bytes(object_key, raw)
        except (RawObjectAlreadyExistsError, ValueError) as exc:
            raise RawLineageError(f"destination publication failed: {object_key}") from exc
        persisted = destination_store.read_bytes(object_key)
        if len(persisted) != row["byte_size"] or sha256_bytes(persisted) != row["sha256_digest"]:
            raise RawLineageError(f"destination verification failed: {object_key}")
        created += 1

    sentinel_created = False
    if not sentinel_reused:
        sentinel = _sentinel_payload(designation, timezone.now())
        try:
            destination_store.write_bytes(SENTINEL_NAME, canonical_json_bytes(sentinel))
        except (RawObjectAlreadyExistsError, ValueError) as exc:
            raise RawLineageError("operational RAW lineage sentinel publication failed") from exc
        sentinel_created = True
    _verify_sentinel(destination_store.read_bytes(SENTINEL_NAME), designation)

    return ConsolidationResult(
        lineage_version=LINEAGE_VERSION,
        manifest_sha256=str(manifest["manifest_sha256"]),
        selected=int(manifest["object_count"]),
        created=created,
        reused=int(manifest["object_count"]) - created,
        dry_run=False,
        sentinel_created=sentinel_created,
        sentinel_reused=sentinel_reused,
        aggregate_byte_count=int(manifest["aggregate_byte_count"]),
    )


def validate_designated_operational_root(
    root: str | Path, expected_manifest_sha256: str
) -> dict[str, Any]:
    root_path = Path(root)
    if not root_path.is_absolute():
        raise RawLineageError("operational RAW root must be an absolute path")
    if not root_path.is_dir():
        raise RawLineageError("operational RAW root does not exist")
    if not expected_manifest_sha256 or not _SHA256_RE.fullmatch(expected_manifest_sha256):
        raise RawLineageError("operational RAW manifest SHA-256 is not configured")
    designation = load_json(DESIGNATION_PATH)
    if designation.get("manifest_sha256") != expected_manifest_sha256:
        raise RawLineageError("configured RAW manifest differs from repository designation")
    store = RawObjectStore(root_path)
    try:
        raw = store.read_bytes(SENTINEL_NAME)
    except FileNotFoundError as exc:
        raise RawLineageError("operational RAW lineage sentinel is missing") from exc
    return _verify_sentinel(raw, designation, expected_manifest_sha256)
