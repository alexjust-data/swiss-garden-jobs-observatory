# mypy: disable-error-code="attr-defined"
from __future__ import annotations

import copy
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from day0.models import (
    Day0AuthorizationPolicy,
    Day0ReadinessSourceEvidence,
    Day0SourceUniverseEntry,
)
from day0.policy import (
    CANTON_SOURCE_CODES,
    KNOWN_AUTOMATION_STATUSES,
    KNOWN_LEGAL_STATUSES,
    VACANCY_CANONICALITY_VALUES,
    access_status_for,
)
from day0.services import (
    _sha256,
    assess_day0_readiness,
    ensure_source_universe,
)
from day0.tests.test_day0 import add_entry, universe, upstream
from reference_data.models import Municipality
from sources.models import Source


@pytest.mark.django_db(transaction=True)
def test_every_policy_id_exists_and_universe_denominator_is_reconciled() -> None:
    call_command("import_reference_data")
    registry_ids = set(Source.objects.values_list("source_id", flat=True))
    assert set(CANTON_SOURCE_CODES) <= registry_ids

    source_universe = ensure_source_universe()
    entries = list(source_universe.entries.all())
    assert len(entries) == 65
    assert sum(row.target_role == "REQUIRED" for row in entries) == 29
    assert sum(row.target_role == "SUPPORTING" for row in entries) == 17
    assert sum(row.classification == "DEFERRED" for row in entries) == 12
    assert sum(row.classification == "NOT_APPLICABLE" for row in entries) == 7
    assert all(row.classification != "BLOCKED_PENDING_ACCESS_REVIEW" for row in entries)
    assert (
        sum(
            row.target_role == "REQUIRED" and row.access_status == "BLOCKED_PENDING_ACCESS_REVIEW"
            for row in entries
        )
        == 29
    )
    assert (
        sum(
            row.target_role == "SUPPORTING" and row.access_status == "BLOCKED_PENDING_ACCESS_REVIEW"
            for row in entries
        )
        == 17
    )

    required = {
        str(row.source_id)
        for row in entries
        if row.target_role == Day0SourceUniverseEntry.TargetRole.REQUIRED
    }
    assert "SRC-OFF-JOBS-ADMIN" in required
    assert set(CANTON_SOURCE_CODES) <= required
    assert {
        "SRC-OFF-CITY-BERN",
        "SRC-OFF-CITY-LUZERN",
        "SRC-OFF-CITY-SCHAFFHAUSEN",
        "SRC-OFF-CITY-STGALLEN",
        "SRC-OFF-CITY-WINTERTHUR",
        "SRC-OFF-CITY-ZURICH",
    } <= required
    assert {
        "SRC-OFF-BFS-COMMUNES",
        "SRC-OFF-JOBROOM-API",
        "SRC-OFF-AMSTAT",
        "SRC-SAL-BFS-SALARIUM",
        "SRC-SAL-JARDINSUISSE-GAV",
        "SRC-SAL-JOBSCH",
        "SRC-SAL-STADT-ZUERICH",
    }.isdisjoint(required)


@pytest.mark.django_db(transaction=True)
def test_every_required_canton_has_governed_german_municipality() -> None:
    call_command("import_reference_data")
    assert set(
        Municipality.objects.filter(canton_code__in=set(CANTON_SOURCE_CODES.values())).values_list(
            "canton_code", flat=True
        )
    ) == set(CANTON_SOURCE_CODES.values())


@pytest.mark.django_db(transaction=True)
def test_access_decision_table_covers_frozen_status_vocabularies() -> None:
    call_command("import_reference_data")
    sources = list(Source.objects.all())
    assert {row.automation_status for row in sources} <= KNOWN_AUTOMATION_STATUSES
    assert {row.legal_review_status for row in sources} <= KNOWN_LEGAL_STATUSES
    for source in sources:
        not_applicable = (
            source.source_family
            in {"OFFICIAL_REFERENCE", "OFFICIAL_STATISTICS", "SALARY_REFERENCE"}
            or source.source_type == "PUBLISHING_API"
        )
        status, _ = access_status_for(source, not_applicable=not_applicable)
        if not_applicable:
            assert status == "NOT_APPLICABLE"
        elif (
            source.automation_status == "READY_FOR_IMPLEMENTATION"
            and source.legal_review_status == "PUBLIC_DATA_DOCUMENTED"
        ):
            assert status == "READY_FOR_IMPLEMENTATION"
        else:
            assert status == "BLOCKED_PENDING_ACCESS_REVIEW"


@pytest.mark.django_db(transaction=True)
def test_canonicality_uses_explicit_values_not_substrings() -> None:
    assert "CANONICAL" in VACANCY_CANONICALITY_VALUES
    assert "HIGH_CANONICALITY" in VACANCY_CANONICALITY_VALUES
    assert "AGENCY_CANONICAL" in VACANCY_CANONICALITY_VALUES
    assert "CANONICAL_REFERENCE" not in VACANCY_CANONICALITY_VALUES
    assert "REFERENCE_CANONICAL" not in VACANCY_CANONICALITY_VALUES
    assert "CANONICAL_STATISTICS" not in VACANCY_CANONICALITY_VALUES


def _clone_run(run, *, finished_at, run_scope, health="HEALTHY"):
    clone = copy.copy(run)
    clone.pk = uuid.uuid4()
    clone.id = clone.pk
    clone._state.adding = True
    clone.started_at = finished_at - timedelta(minutes=5)
    clone.finished_at = finished_at
    clone.run_scope = run_scope
    clone.status = "SUCCEEDED"
    clone.source_health_status = health
    if run_scope != "FULL_SOURCE":
        clone.snapshot_complete = False
    clone.save(force_insert=True)
    return clone


@pytest.mark.django_db(transaction=True)
def test_later_targeted_activity_does_not_erase_full_snapshot_but_updates_health() -> None:
    data, snapshot = upstream(suffix="run-selection")
    full = data["observation"].collection_run
    full.finished_at = data["as_of"] - timedelta(hours=2)
    full.save(update_fields=["finished_at"])
    targeted = _clone_run(
        full,
        finished_at=data["as_of"] - timedelta(hours=1),
        run_scope="TARGETED",
    )
    source_universe = universe()
    add_entry(source_universe, data["source"])

    assessment, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
    )
    evidence = assessment.source_evidence.get()
    assert evidence.latest_full_source_run_id == full.pk
    assert evidence.latest_activity_run_id == targeted.pk
    assert evidence.structurally_complete
    assert evidence.currently_healthy


@pytest.mark.django_db(transaction=True)
def test_later_outage_changes_health_and_fingerprint_without_rewriting_full_snapshot() -> None:
    data, snapshot = upstream(suffix="health-after-full")
    full = data["observation"].collection_run
    full.finished_at = data["as_of"] - timedelta(hours=2)
    full.save(update_fields=["finished_at"])
    source_universe = universe()
    add_entry(source_universe, data["source"])
    first, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
    )
    outage = _clone_run(
        full,
        finished_at=data["as_of"] - timedelta(minutes=30),
        run_scope="TARGETED",
        health="OUTAGE",
    )
    second, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
    )
    row = second.source_evidence.get()
    assert row.latest_full_source_run_id == full.pk
    assert row.latest_health_run_id == outage.pk
    assert row.structurally_complete and not row.currently_healthy
    assert second.input_fingerprint != first.input_fingerprint
    first.refresh_from_db()
    assert first.source_evidence.get().latest_health_run_id == full.pk


@pytest.mark.django_db(transaction=True)
def test_freshness_is_pending_until_separate_policy_is_accepted() -> None:
    data, snapshot = upstream(suffix="freshness")
    full = data["observation"].collection_run
    full.finished_at = data["as_of"] - timedelta(hours=2)
    full.save(update_fields=["finished_at"])
    source_universe = universe()
    add_entry(source_universe, data["source"])

    pending, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
    )
    assert pending.metrics["required_source_freshness_coverage"]["status"] == "POLICY_PENDING"
    assert pending.source_evidence.get().freshness_valid is None

    accepted = Day0AuthorizationPolicy.objects.create(
        policy_version="fixture-freshness-v1",
        threshold_policy_status="ACCEPTED",
        required_completion_threshold=Decimal("1"),
        freshness_policy_status="ACCEPTED",
        required_source_max_age_hours=1,
        configuration={"fixture": True},
        input_fingerprint=_sha256({"fixture": "freshness"}),
    )
    source_universe.policy_version = accepted.policy_version
    source_universe._state.adding = True
    source_universe.pk = uuid.uuid4()
    source_universe.input_fingerprint = "a" * 64
    source_universe.save(force_insert=True)
    entry = add_entry(source_universe, data["source"])
    stale, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
        authorization_policy=accepted,
    )
    assert stale.source_evidence.get(universe_entry=entry).freshness_valid is False
    assert stale.readiness_status == "DAY_0_NOT_READY"


@pytest.mark.django_db(transaction=True)
def test_source_evidence_rejects_collection_run_from_another_source() -> None:
    data, snapshot = upstream(suffix="cross-object")
    other, _ = upstream(suffix="cross-object-other", as_of=data["as_of"])
    source_universe = universe()
    entry = add_entry(source_universe, data["source"])
    assessment, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
    )
    invalid = Day0ReadinessSourceEvidence(
        assessment=assessment,
        universe_entry=entry,
        source=data["source"],
        latest_full_source_run=other["observation"].collection_run,
        completion_status="INCOMPLETE",
    )
    with pytest.raises(ValidationError):
        invalid.full_clean()


def test_persisted_ratio_is_deterministically_quantized() -> None:
    from day0.services import _persisted_ratio

    assert _persisted_ratio(2, 29) == Decimal("0.068966")
