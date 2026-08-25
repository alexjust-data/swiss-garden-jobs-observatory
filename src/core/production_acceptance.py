from __future__ import annotations

import hashlib
import json
import math
import os
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import OpenerDirector

from django.apps import apps
from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder

from core.models import RawArtifact
from core.raw_lineage import RawLineageError, validate_designated_operational_root
from core.storage import RawObjectStore
from observations.geospatial import GeoAdminSearchServerClient
from observations.geospatial_batch import GeospatialBatchResult, resolve_premium_run_locations

REPORT_VERSION = "production-acceptance-v0.1"
OPERATION_GEOSPATIAL = "geospatial-recovery"
GOVERNED_APP_LABELS = frozenset(
    {
        "core",
        "sources",
        "reference_data",
        "observations",
        "vacancies",
        "premium_segments",
        "dashboard",
        "day0",
        "operations",
    }
)
ARTIFACT_SUMMARY_FIELDS: dict[str, tuple[str, ...]] = {
    "vacancies.DedupRun": ("id", "as_of", "status", "input_fingerprint"),
    "premium_segments.PremiumSegmentRun": ("id", "as_of", "status", "input_fingerprint"),
    "dashboard.DashboardSnapshot": ("id", "as_of", "input_fingerprint"),
    "day0.Day0ReadinessAssessment": (
        "id",
        "as_of",
        "readiness_status",
        "input_fingerprint",
    ),
    "operations.ObservatoryCycle": (
        "id",
        "status",
        "final_cutoff",
        "dedup_run",
        "premium_run",
        "dashboard_snapshot",
        "readiness_assessment",
        "configuration_fingerprint",
    ),
}
GEOSPATIAL_ALLOWED_CREATES = frozenset(
    {
        "core.RawArtifact",
        "observations.GeocoderCacheEntry",
        "observations.PostingLocationResolution",
        "observations.GeocodingReviewItem",
    }
)


class AcceptanceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_PROVEN = "NOT_PROVEN"


class ProductionAcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: AcceptanceStatus
    mandatory: bool
    summary: str
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class HttpEvidence:
    provider_fetches: int
    provider_transport_requests: int
    source_transport_requests: int


class ProviderHttpRecorder:
    """Count governed urllib traffic without retaining URLs or query material."""

    def __init__(self) -> None:
        self.provider_fetches = 0
        self.provider_transport_requests = 0
        self.source_transport_requests = 0
        self._original_fetch: Any = None
        self._original_open: Any = None

    def __enter__(self) -> ProviderHttpRecorder:
        self._original_fetch = GeoAdminSearchServerClient.fetch
        self._original_open = OpenerDirector.open
        recorder = self

        def audited_fetch(client: Any, request_data: dict[str, object]) -> Any:
            recorder.provider_fetches += 1
            return recorder._original_fetch(client, request_data)

        def audited_open(opener: Any, fullurl: Any, *args: Any, **kwargs: Any) -> Any:
            candidate = getattr(fullurl, "full_url", fullurl)
            host = (urlsplit(str(candidate)).hostname or "").casefold()
            if host == "api3.geo.admin.ch":
                recorder.provider_transport_requests += 1
            else:
                recorder.source_transport_requests += 1
            return recorder._original_open(opener, fullurl, *args, **kwargs)

        GeoAdminSearchServerClient.fetch = audited_fetch  # type: ignore[method-assign,assignment]
        OpenerDirector.open = audited_open  # type: ignore[method-assign,assignment]
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        GeoAdminSearchServerClient.fetch = self._original_fetch  # type: ignore[method-assign]
        OpenerDirector.open = self._original_open  # type: ignore[method-assign]

    def evidence(self) -> HttpEvidence:
        return HttpEvidence(
            provider_fetches=self.provider_fetches,
            provider_transport_requests=self.provider_transport_requests,
            source_transport_requests=self.source_transport_requests,
        )


def _canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProductionAcceptanceError("naive datetimes are not canonical evidence")
    utc_value = value.astimezone(UTC)
    return utc_value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProductionAcceptanceError("non-finite floats are not canonical evidence")
        return value
    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID | Decimal | Path):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Mapping):
        return {
            str(key): canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list | tuple):
        return [canonical_value(item) for item in value]
    raise ProductionAcceptanceError(f"unsupported canonical evidence type: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def governed_model_labels() -> tuple[str, ...]:
    """Return the complete governed project-model surface in canonical order."""

    return tuple(
        sorted(
            model._meta.label
            for model in apps.get_models()
            if model._meta.app_label in GOVERNED_APP_LABELS
        )
    )


def _model_rows(model_label: str) -> dict[str, str]:
    model = apps.get_model(model_label)
    fields = tuple(model._meta.concrete_fields)
    rows: dict[str, str] = {}
    for item in model._default_manager.order_by("pk").iterator(chunk_size=500):
        payload = {field.name: canonical_value(getattr(item, field.attname)) for field in fields}
        pk = str(item.pk)
        rows[pk] = sha256({"model": model_label, "pk": pk, "fields": payload})
    return rows


def _raw_evidence(*, verify_bytes: bool) -> dict[str, Any]:
    root = Path(settings.CORE_RAW_OBJECT_STORE_PATH).resolve()
    root_identity = hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()
    if not verify_bytes:
        return {
            "status": AcceptanceStatus.NOT_PROVEN.value,
            "root_identity_sha256": root_identity,
            "verified": 0,
            "missing": 0,
            "conflicting": 0,
            "physical_inventory_sha256": None,
        }
    store = RawObjectStore(root)
    verified: list[tuple[str, str, int]] = []
    missing: list[str] = []
    conflicting: list[str] = []
    for artifact in RawArtifact.objects.order_by("object_key").iterator(chunk_size=250):
        identity = hashlib.sha256(artifact.object_key.encode("utf-8")).hexdigest()
        try:
            content = store.read_bytes(artifact.object_key)
        except (FileNotFoundError, OSError, ValueError):
            missing.append(identity)
            continue
        digest = hashlib.sha256(content).hexdigest()
        if digest != artifact.sha256_digest or len(content) != artifact.byte_size:
            conflicting.append(identity)
            continue
        verified.append((artifact.object_key, digest, len(content)))
    status = AcceptanceStatus.PASS if not missing and not conflicting else AcceptanceStatus.FAIL
    return {
        "status": status.value,
        "root_identity_sha256": root_identity,
        "verified": len(verified),
        "missing": len(missing),
        "conflicting": len(conflicting),
        "missing_identity_sha256": sorted(missing),
        "conflicting_identity_sha256": sorted(conflicting),
        "physical_inventory_sha256": sha256(verified),
    }


def _database_metadata() -> dict[str, Any]:
    if connection.vendor != "postgresql":
        raise ProductionAcceptanceError("H2 v0.1 requires PostgreSQL snapshot semantics")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), txid_current_snapshot()::text, "
            "transaction_timestamp(), inet_server_addr()::text, inet_server_port(), version()"
        )
        database, snapshot_id, started_at, address, port, version = cursor.fetchone()
    server_identity = sha256(
        {
            "address": address or "local-socket",
            "port": port,
            "version": str(version).split(",", 1)[0],
        }
    )
    database_identity = sha256(
        {
            "vendor": connection.vendor,
            "database": database,
            "server_identity_sha256": server_identity,
        }
    )
    migrations = sorted(
        [app_name, migration_name]
        for app_name, migration_name in MigrationRecorder.Migration.objects.values_list(
            "app", "name"
        )
    )
    return {
        "vendor": connection.vendor,
        "database": database,
        "transaction_snapshot": snapshot_id,
        "transaction_started_at": canonical_value(started_at),
        "server_identity_sha256": server_identity,
        "database_identity_sha256": database_identity,
        "migration_count": len(migrations),
        "migration_inventory_sha256": sha256(migrations),
    }


def _artifact_summaries() -> dict[str, list[dict[str, Any]]]:
    summaries: dict[str, list[dict[str, Any]]] = {}
    for model_label, field_names in ARTIFACT_SUMMARY_FIELDS.items():
        model = apps.get_model(model_label)
        rows: list[dict[str, Any]] = []
        for item in model._default_manager.order_by("pk").iterator(chunk_size=250):
            payload: dict[str, Any] = {}
            for field_name in field_names:
                field = model._meta.get_field(field_name)
                payload[field_name] = canonical_value(getattr(item, field.attname))
            rows.append(payload)
        summaries[model_label] = rows
    return summaries


def current_database_identity() -> dict[str, str]:
    """Return bounded server/database authority without credentials or DSNs."""

    metadata = _database_metadata()
    return {
        "database": str(metadata["database"]),
        "server_identity_sha256": str(metadata["server_identity_sha256"]),
        "database_identity_sha256": str(metadata["database_identity_sha256"]),
    }


def capture_snapshot(*, verify_raw_bytes: bool) -> dict[str, Any]:
    if connection.in_atomic_block:
        raise ProductionAcceptanceError("H2 snapshots require their own database transaction")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        metadata = _database_metadata()
        model_labels = governed_model_labels()
        models: dict[str, Any] = {}
        for model_label in model_labels:
            rows = _model_rows(model_label)
            models[model_label] = {
                "count": len(rows),
                "inventory_sha256": sha256(sorted(rows.items())),
                "rows": rows,
            }
        artifacts = _artifact_summaries()
        raw = _raw_evidence(verify_bytes=verify_raw_bytes)
    return {
        "database": metadata,
        "governed_model_labels": list(model_labels),
        "model_inventory_sha256": sha256(model_labels),
        "models": models,
        "artifacts": artifacts,
        "raw": raw,
        "snapshot_sha256": sha256(
            {"database": metadata, "models": models, "artifacts": artifacts, "raw": raw}
        ),
    }


def compare_snapshots(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    before_labels = tuple(before["governed_model_labels"])
    after_labels = tuple(after["governed_model_labels"])
    if before_labels != after_labels:
        raise ProductionAcceptanceError("governed model inventory changed during acceptance")
    if before.get("model_inventory_sha256") != after.get("model_inventory_sha256"):
        raise ProductionAcceptanceError("governed model inventory fingerprint changed")
    for model_label in before_labels:
        before_rows = dict(before["models"][model_label]["rows"])
        after_rows = dict(after["models"][model_label]["rows"])
        before_ids = set(before_rows)
        after_ids = set(after_rows)
        result[model_label] = {
            "created": sorted(after_ids - before_ids),
            "deleted": sorted(before_ids - after_ids),
            "modified": sorted(
                identity
                for identity in before_ids & after_ids
                if before_rows[identity] != after_rows[identity]
            ),
        }
    return result


def _check(
    check_id: str,
    status: AcceptanceStatus,
    summary: str,
    *,
    mandatory: bool = True,
    details: Mapping[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(check_id, status, mandatory, summary, details or {})


def _aggregate(checks: Sequence[CheckResult]) -> AcceptanceStatus:
    mandatory = [item for item in checks if item.mandatory]
    if any(item.status == AcceptanceStatus.FAIL for item in mandatory):
        return AcceptanceStatus.FAIL
    if any(item.status == AcceptanceStatus.NOT_PROVEN for item in mandatory):
        return AcceptanceStatus.NOT_PROVEN
    return AcceptanceStatus.PASS


def _delta_checks(
    delta: Mapping[str, Any],
    *,
    allowed_creates: frozenset[str],
    retry: bool,
) -> list[CheckResult]:
    prefix = "retry" if retry else "operation"
    deleted = {label: values["deleted"] for label, values in delta.items() if values["deleted"]}
    modified = {label: values["modified"] for label, values in delta.items() if values["modified"]}
    unexpected_created = {
        label: values["created"]
        for label, values in delta.items()
        if values["created"] and (retry or label not in allowed_creates)
    }
    return [
        _check(
            f"{prefix}_historical_deletes",
            AcceptanceStatus.FAIL if deleted else AcceptanceStatus.PASS,
            "historical rows deleted" if deleted else "no historical rows deleted",
            details={"models": deleted},
        ),
        _check(
            f"{prefix}_historical_mutations",
            AcceptanceStatus.FAIL if modified else AcceptanceStatus.PASS,
            "historical rows modified" if modified else "no historical rows modified",
            details={"models": modified},
        ),
        _check(
            f"{prefix}_unexpected_creates",
            AcceptanceStatus.FAIL if unexpected_created else AcceptanceStatus.PASS,
            "unexpected rows created"
            if unexpected_created
            else "created rows respect adapter boundary",
            details={"models": unexpected_created},
        ),
    ]


def _operational_root_preflight(
    *,
    execute: bool,
    allow_operational: bool,
    database_identity: Mapping[str, str],
) -> dict[str, Any]:
    database = database_identity["database"]
    operational_database = str(settings.JOB_OBSERVATORY_OPERATIONAL_DB_NAME)
    is_operational = database == operational_database
    configured_identity = str(settings.JOB_OBSERVATORY_OPERATIONAL_DB_IDENTITY_SHA256).strip()
    if is_operational and configured_identity != database_identity["database_identity_sha256"]:
        raise ProductionAcceptanceError("operational database identity designation mismatch")
    execution_path = Path(settings.CORE_RAW_OBJECT_STORE_PATH)
    operational_path = Path(settings.JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH)
    execution_root = os.path.normcase(str(execution_path.resolve()))
    operational_root = os.path.normcase(str(operational_path.resolve()))
    if not execute:
        return {"is_operational": is_operational, "designation_verified": False}
    if not execution_path.is_absolute() or not operational_path.is_absolute():
        raise ProductionAcceptanceError("mutable H2 RAW roots must be absolute")
    if not is_operational and execution_root == operational_root:
        raise ProductionAcceptanceError(
            "isolated database must use a RAW root distinct from the operational root"
        )
    if is_operational and not allow_operational:
        raise ProductionAcceptanceError(
            "operational execution requires the explicit --allow-operational boundary"
        )
    if is_operational:
        try:
            validate_designated_operational_root(
                settings.CORE_RAW_OBJECT_STORE_PATH,
                str(settings.JOB_OBSERVATORY_RAW_LINEAGE_MANIFEST_SHA256),
            )
        except RawLineageError as exc:
            raise ProductionAcceptanceError(str(exc)) from exc
    return {"is_operational": is_operational, "designation_verified": is_operational}


def _result_dict(result: GeospatialBatchResult | None) -> dict[str, Any] | None:
    return result.to_dict() if result is not None else None


def run_geospatial_acceptance(
    *,
    premium_run_id: str,
    expected_database: str,
    expected_database_identity_sha256: str,
    execute: bool,
    allow_operational: bool,
    verify_raw_bytes: bool,
) -> dict[str, Any]:
    database_identity = current_database_identity()
    if not expected_database or expected_database != database_identity["database"]:
        raise ProductionAcceptanceError("connected database does not match --expected-database")
    if (
        len(expected_database_identity_sha256) != 64
        or expected_database_identity_sha256 != expected_database_identity_sha256.lower()
        or any(
            character not in "0123456789abcdef" for character in expected_database_identity_sha256
        )
        or expected_database_identity_sha256 != database_identity["database_identity_sha256"]
    ):
        raise ProductionAcceptanceError(
            "connected server/database does not match --expected-database-identity-sha256"
        )
    if execute and not verify_raw_bytes:
        raise ProductionAcceptanceError("mutable H2 acceptance requires --verify-raw-bytes")
    root_preflight = _operational_root_preflight(
        execute=execute,
        allow_operational=allow_operational,
        database_identity=database_identity,
    )
    started = time.monotonic()
    before = capture_snapshot(verify_raw_bytes=verify_raw_bytes)
    checks: list[CheckResult] = [
        _check(
            "database_identity",
            AcceptanceStatus.PASS,
            "connected database matches the explicit expected identity",
            details={**database_identity, **root_preflight},
        ),
        _check(
            "raw_before",
            AcceptanceStatus(before["raw"]["status"]),
            "pre-operation RAW bytes verified"
            if before["raw"]["status"] == AcceptanceStatus.PASS
            else "pre-operation RAW bytes are not fully verified",
            details={key: before["raw"][key] for key in ("verified", "missing", "conflicting")},
        ),
    ]
    operation: GeospatialBatchResult | None = None
    retry_result: GeospatialBatchResult | None = None
    provider_first = HttpEvidence(0, 0, 0)
    provider_retry = HttpEvidence(0, 0, 0)
    operation_error: str | None = None

    if before["raw"]["status"] == AcceptanceStatus.FAIL:
        operation_error = "RAW_PREFLIGHT_FAILED"
    elif not execute:
        operation = resolve_premium_run_locations(premium_run_id, dry_run=True)
    else:
        try:
            with ProviderHttpRecorder() as recorder:
                operation = resolve_premium_run_locations(premium_run_id)
            provider_first = recorder.evidence()
        except Exception as exc:  # bounded report; never serialize exception text
            operation_error = type(exc).__name__

    after = capture_snapshot(verify_raw_bytes=verify_raw_bytes)
    operation_delta = compare_snapshots(before, after)
    checks.extend(
        _delta_checks(
            operation_delta,
            allowed_creates=GEOSPATIAL_ALLOWED_CREATES,
            retry=False,
        )
    )

    if execute and operation is not None and operation_error is None:
        created_resolutions = operation_delta["observations.PostingLocationResolution"]["created"]
        batch_consistent = bool(
            len(created_resolutions) == operation.created
            and len(operation.resolution_ids) == operation.selected
            and set(created_resolutions).issubset(set(operation.resolution_ids))
        )
        checks.append(
            _check(
                "geospatial_batch_identity",
                AcceptanceStatus.PASS if batch_consistent else AcceptanceStatus.FAIL,
                "batch counts and exact resolution identities agree"
                if batch_consistent
                else "batch counts differ from database identity deltas",
                details={
                    "reported_created": operation.created,
                    "observed_created": len(created_resolutions),
                    "reported_selected": operation.selected,
                    "observed_resolution_ids": len(operation.resolution_ids),
                },
            )
        )
    if not execute:
        checks.append(
            _check(
                "operation_executed",
                AcceptanceStatus.NOT_PROVEN,
                "dry-run preflight did not execute the mutable operation",
            )
        )
    elif operation_error:
        checks.append(
            _check(
                "operation_executed",
                AcceptanceStatus.FAIL,
                "operation failed",
                details={"error_type": operation_error},
            )
        )
    else:
        checks.append(_check("operation_executed", AcceptanceStatus.PASS, "operation completed"))

    retry_snapshot: dict[str, Any] | None = None
    retry_delta: dict[str, Any] | None = None
    if execute and operation is not None and operation_error is None:
        try:
            with ProviderHttpRecorder() as recorder:
                retry_result = resolve_premium_run_locations(premium_run_id)
            provider_retry = recorder.evidence()
        except Exception as exc:
            operation_error = f"RETRY_{type(exc).__name__}"
        retry_snapshot = capture_snapshot(verify_raw_bytes=verify_raw_bytes)
        retry_delta = compare_snapshots(after, retry_snapshot)
        checks.extend(
            _delta_checks(
                retry_delta,
                allowed_creates=frozenset(),
                retry=True,
            )
        )
        exact = bool(
            retry_result
            and retry_result.created == 0
            and retry_result.network_requests == 0
            and operation.resolution_ids == retry_result.resolution_ids
            and operation.premium_run_fingerprint == retry_result.premium_run_fingerprint
            and not operation_error
        )
        checks.append(
            _check(
                "exact_retry",
                AcceptanceStatus.PASS if exact else AcceptanceStatus.FAIL,
                "exact retry reused governed evidence" if exact else "exact retry diverged",
            )
        )
        provider_consistent = bool(
            provider_first.provider_fetches == operation.network_requests
            and retry_result
            and provider_retry.provider_fetches == retry_result.network_requests == 0
        )
        checks.append(
            _check(
                "provider_http",
                AcceptanceStatus.PASS if provider_consistent else AcceptanceStatus.FAIL,
                "provider fetch instrumentation matches batch evidence"
                if provider_consistent
                else "provider fetch instrumentation differs from batch evidence",
                details={
                    "first_fetches": provider_first.provider_fetches,
                    "retry_fetches": provider_retry.provider_fetches,
                    "first_transport_requests": provider_first.provider_transport_requests,
                    "retry_transport_requests": provider_retry.provider_transport_requests,
                },
            )
        )
        source_requests = (
            provider_first.source_transport_requests + provider_retry.source_transport_requests
        )
        checks.append(
            _check(
                "source_http",
                AcceptanceStatus.PASS if source_requests == 0 else AcceptanceStatus.FAIL,
                "no Source HTTP transport observed"
                if source_requests == 0
                else "unexpected non-provider HTTP transport observed",
                details={
                    "requests": source_requests,
                    "instrumentation": "urllib OpenerDirector.open",
                },
            )
        )
    else:
        checks.extend(
            [
                _check(
                    "exact_retry",
                    AcceptanceStatus.NOT_PROVEN,
                    "exact retry was not executed",
                ),
                _check(
                    "provider_http",
                    AcceptanceStatus.NOT_PROVEN,
                    "provider HTTP was not accepted as production evidence",
                ),
                _check(
                    "source_http",
                    AcceptanceStatus.NOT_PROVEN,
                    "Source HTTP was not accepted as production evidence",
                ),
            ]
        )

    raw_after_status = AcceptanceStatus(after["raw"]["status"])
    checks.append(
        _check(
            "raw_after",
            raw_after_status,
            "post-operation RAW bytes verified"
            if raw_after_status == AcceptanceStatus.PASS
            else "post-operation RAW bytes are not fully verified",
            details={key: after["raw"][key] for key in ("verified", "missing", "conflicting")},
        )
    )
    overall = _aggregate(checks)
    stable = {
        "report_version": REPORT_VERSION,
        "operation": OPERATION_GEOSPATIAL,
        "execution_requested": execute,
        "expected_database": expected_database,
        "expected_database_identity_sha256": expected_database_identity_sha256,
        "before": before,
        "operation_result": _result_dict(operation),
        "after": after,
        "operation_delta": operation_delta,
        "retry_result": _result_dict(retry_result),
        "retry_snapshot": retry_snapshot,
        "retry_delta": retry_delta,
        "checks": [item.to_dict() for item in checks],
        "overall": overall.value,
    }
    return {
        **stable,
        "evidence_sha256": sha256(stable),
        "volatile": {"duration_seconds": round(time.monotonic() - started, 6)},
    }


def _assert_output_scope(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    raw_roots = (
        Path(settings.CORE_RAW_OBJECT_STORE_PATH).resolve(),
        Path(settings.JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH).resolve(),
    )
    if any(
        resolved == root or root in resolved.parents or resolved in root.parents
        for root in raw_roots
    ):
        raise ProductionAcceptanceError(
            "report output and execution/operational RAW roots must be disjoint"
        )
    resolved.mkdir(parents=True, exist_ok=True)
    probe = resolved / f".h2-write-probe-{uuid.uuid4().hex}"
    try:
        with probe.open("xb") as stream:
            stream.write(b"H2")
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        probe.unlink(missing_ok=True)
    return resolved


def write_report(report: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path]:
    destination = _assert_output_scope(output_dir)
    json_path = destination / "production-acceptance.json"
    text_path = destination / "production-acceptance.txt"
    json_bytes = (
        json.dumps(canonical_value(report), ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
    checks = report["checks"]
    lines = [
        "PRODUCTION ACCEPTANCE H2",
        "",
        f"Operation: {report['operation']}",
        f"Overall: {report['overall']}",
        f"Evidence SHA-256: {report['evidence_sha256']}",
        "",
    ]
    for check in checks:
        lines.append(
            f"{check['check_id']:<34} {check['status']:<10} "
            f"[{'mandatory' if check['mandatory'] else 'informational'}] {check['summary']}"
        )
    lines.extend(["", "MECHANICAL EVIDENCE ONLY — INDEPENDENT AUDIT STILL REQUIRED", ""])
    text_bytes = "\n".join(lines).encode("utf-8")
    for path, content in ((json_path, json_bytes), (text_path, text_bytes)):
        temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    return json_path, text_path
