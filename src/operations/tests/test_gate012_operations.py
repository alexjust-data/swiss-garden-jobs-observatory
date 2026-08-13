from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from dashboard.services import build_dashboard_snapshot
from dashboard.tests.factories import create_dashboard_upstream
from day0.tests.test_day0 import add_entry, assess, complete_collection, universe
from observations.models import CollectionRun
from operations.models import (
    ImmutableOperationalEvidenceError,
    ObservatoryCycle,
    ObservatorySourceAttempt,
    OperationalEvent,
)
from operations.services import (
    CYCLE_VERSION,
    _event,
    cycle_configuration,
    cycle_summary,
    observatory_status,
    run_cycle,
)
from sources.models import Source

pytestmark = pytest.mark.django_db


def source(suffix: str = "1") -> Source:
    return Source.objects.create(
        source_id=f"TEST-OPS-{suffix}",
        source_name=f"Operations source {suffix}",
        domain=f"ops{suffix}.example",
        source_family="OFFICIAL_CANTON",
        source_type="PUBLIC_OFFICIAL_EMPLOYER",
        priority="P0",
        coverage_scope="fixture",
        canonicality="CANONICAL",
        platform_family="FIXTURE",
        access_method="HTML",
        automation_status="READY_FOR_IMPLEMENTATION",
        legal_review_status="PUBLIC_DATA_DOCUMENTED",
        verification_status="VERIFIED",
        official_url=f"https://ops{suffix}.example/jobs",
    )


def configuration(trigger: str, sources: list[Source]) -> tuple[dict[str, object], str]:
    from operations.services import _sha256

    value = cycle_configuration(trigger, [str(item.pk) for item in sources])
    return value, _sha256(value)


def cycle(*, status: str = "PLANNED", suffix: str = "1") -> ObservatoryCycle:
    src = source(suffix)
    config, fingerprint = configuration("MANUAL", [src])
    finished = timezone.now() if status in ObservatoryCycle.TERMINAL else None
    return ObservatoryCycle.objects.create(
        cycle_version=CYCLE_VERSION,
        trigger="MANUAL",
        status=status,
        finished_at=finished,
        target_cohort_version="day0-source-universe-v0.2",
        selected_source_ids=[str(src.pk)],
        configuration=config,
        configuration_fingerprint=fingerprint,
        stage_statuses={},
    )


def successful_run(src: Source) -> CollectionRun:
    now = timezone.now()
    return CollectionRun.objects.create(
        source=src,
        started_at=now,
        finished_at=now,
        status="SUCCEEDED",
        run_scope="FULL_SOURCE",
        snapshot_complete=True,
        source_health_status="HEALTHY",
        listing_url=src.official_url,
        listings_discovered=1,
        listing_total_discovered=1,
        postings_in_scope=1,
        details_fetched=1,
        observations_created=1,
        green_assessments_created=1,
    )


def test_completed_cycle_is_immutable() -> None:
    item = cycle(status="SUCCEEDED_NOT_AUTHORIZED")
    item.operational_health = "RED"
    with pytest.raises(ImmutableOperationalEvidenceError):
        item.save()


def test_final_cutoff_requires_complete_pit_chain() -> None:
    item = cycle()
    item.final_cutoff = timezone.now()
    item.finished_at = timezone.now()
    with pytest.raises(ValidationError):
        item.full_clean()


def test_source_attempt_is_append_only_and_pins_matching_source() -> None:
    item = cycle()
    src = Source.objects.get(pk=item.selected_source_ids[0])
    run = successful_run(src)
    attempt = ObservatorySourceAttempt.objects.create(
        cycle=item,
        source=src,
        collection_run=run,
        result="SUCCEEDED",
        started_at=run.started_at,
        finished_at=run.finished_at,
        run_status="SUCCEEDED",
        source_health="HEALTHY",
        snapshot_complete=True,
        counter_consistent=True,
    )
    attempt.failure_code = "FORGED"
    with pytest.raises(ImmutableOperationalEvidenceError):
        attempt.save()


def test_source_attempt_rejects_foreign_collection_run() -> None:
    item = cycle()
    selected = Source.objects.get(pk=item.selected_source_ids[0])
    other = source("other")
    run = successful_run(other)
    attempt = ObservatorySourceAttempt(
        cycle=item,
        source=selected,
        collection_run=run,
        result="SUCCEEDED",
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
    with pytest.raises(ValidationError):
        attempt.full_clean()


def test_event_deduplicates_unchanged_known_condition() -> None:
    item = cycle()
    first = _event(item, "KNOWN_STRUCTURAL_BLOCKER", "INFO", detail={"coverage": "20/29"})
    second = _event(item, "KNOWN_STRUCTURAL_BLOCKER", "INFO", detail={"coverage": "20/29"})
    assert first.pk == second.pk
    assert OperationalEvent.objects.filter(cycle=item).count() == 1


def test_configuration_is_deterministic_and_source_order_independent() -> None:
    left = source("left")
    right = source("right")
    a, a_fp = configuration("SCHEDULED", [left, right])
    b, b_fp = configuration("SCHEDULED", [right, left])
    assert a == b
    assert a_fp == b_fp


@contextmanager
def refused_lock():
    yield False


def test_concurrent_cycle_refuses_before_collector_activity() -> None:
    src = source()
    collector = Mock()
    universe = SimpleNamespace(universe_version="day0-source-universe-v0.2")
    with (
        patch("operations.services.governed_source_cohort", return_value=(universe, [src])),
        patch("operations.services.cycle_lock", refused_lock),
    ):
        result = run_cycle(collector=collector)
    assert result.cycle.status == "ABORTED_CONCURRENCY"
    assert result.cycle.failure_evidence == {"http_requests": 0}
    collector.assert_not_called()
    assert result.cycle.source_attempts.count() == 0


def test_collection_failure_is_persisted_without_false_downstream_success() -> None:
    src = source()
    universe = SimpleNamespace(universe_version="day0-source-universe-v0.2")
    collector = Mock(side_effect=RuntimeError("bounded HTTP failure"))
    with (
        patch("operations.services.governed_source_cohort", return_value=(universe, [src])),
        patch("operations.services.apply_green_continuity", side_effect=RuntimeError("stop")),
    ):
        result = run_cycle(collector=collector)
    assert result.cycle.status == "FAILED_CONTINUITY"
    attempt = result.cycle.source_attempts.get()
    assert attempt.result == "FAILED"
    assert attempt.collection_run is None
    assert result.cycle.dedup_run is None


def test_successful_same_cycle_retry_has_no_network_side_effect() -> None:
    src = source()
    universe = SimpleNamespace(universe_version="day0-source-universe-v0.2")
    config, fingerprint = configuration("MANUAL", [src])
    item = ObservatoryCycle.objects.create(
        cycle_version=CYCLE_VERSION,
        trigger="MANUAL",
        status="SUCCEEDED_NOT_AUTHORIZED",
        finished_at=timezone.now(),
        target_cohort_version=universe.universe_version,
        selected_source_ids=[str(src.pk)],
        configuration=config,
        configuration_fingerprint=fingerprint,
        stage_statuses={},
    )
    collector = Mock()
    with patch("operations.services.governed_source_cohort", return_value=(universe, [src])):
        result = run_cycle(cycle_id=item.pk, collector=collector)
    assert result.reused is True
    assert result.cycle.pk == item.pk
    collector.assert_not_called()


def test_retry_requires_identical_configuration() -> None:
    item = cycle(status="FAILED_COLLECTION")
    src = Source.objects.get(pk=item.selected_source_ids[0])
    universe = SimpleNamespace(universe_version="day0-source-universe-v0.2")
    with (
        patch("operations.services.governed_source_cohort", return_value=(universe, [src])),
        patch("operations.services._git_sha", return_value="a" * 40),
        pytest.raises(Exception, match="configuration differs"),
    ):
        run_cycle(cycle_id=item.pk, resume=True)


def test_status_is_deterministic_and_preserves_history() -> None:
    first = cycle(status="SUCCEEDED_NOT_AUTHORIZED", suffix="first")
    assert first.finished_at is not None
    second = cycle(status="FAILED_COLLECTION", suffix="second")
    before = cycle_summary(first)
    one = observatory_status(at=timezone.now())
    two = observatory_status(at=timezone.now())
    assert one["latest_cycle"]["cycle_id"] == str(second.pk)
    assert one["last_successful_cycle_id"] == str(first.pk)
    assert one["quality_state"] == two["quality_state"]
    assert cycle_summary(first) == before


def test_status_command_emits_json() -> None:
    item = cycle(status="SUCCEEDED_NOT_AUTHORIZED")
    output = StringIO()
    call_command("observatory_status", "--json", stdout=output)
    payload = json.loads(output.getvalue())
    assert payload["latest_cycle"]["cycle_id"] == str(item.pk)


def test_cycle_identity_is_uuid_and_new_cycle_is_distinct() -> None:
    first = cycle(suffix="one")
    second = cycle(suffix="two")
    assert isinstance(first.pk, uuid.UUID)
    assert first.pk != second.pk


def test_complete_cycle_orders_stages_and_pins_aligned_artifacts() -> None:
    data = create_dashboard_upstream(suffix="ops-complete")
    complete_collection(data)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    source_universe = universe()
    add_entry(source_universe, data["source"])
    readiness, _ = assess(data, snapshot, source_universe)
    continuity = {"created": 0, "reused": 0, "unmatched": 0, "conflicts": 0}
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services.apply_green_continuity", return_value=continuity),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch("operations.services.run_classification", return_value=(data["premium_run"], True)),
        patch("operations.services.build_dashboard_snapshot", return_value=(snapshot, True)),
        patch("operations.services.assess_day0_readiness", return_value=(readiness, True)),
        patch("operations.services.timezone.now", return_value=data["as_of"]),
    ):
        result = run_cycle(collector=Mock(return_value=data["observation"].collection_run))
    item = result.cycle
    assert item.status == "SUCCEEDED_NOT_AUTHORIZED"
    assert item.operational_health == "GREEN"
    assert item.final_cutoff == data["as_of"]
    assert list(item.stage_statuses) == [
        "cohort",
        "collection",
        "green_continuity",
        "dedup",
        "dedup_continuity",
        "premium",
        "dashboard",
        "readiness",
    ]
    assert set(item.stage_statuses.values()) == {"SUCCEEDED"}
    assert item.dedup_run == data["dedup"]
    assert item.premium_run == data["premium_run"]
    assert item.dashboard_snapshot == snapshot
    assert item.readiness_assessment == readiness


def test_dashboard_failure_has_stage_specific_terminal_state() -> None:
    data = create_dashboard_upstream(suffix="ops-dashboard-failure")
    complete_collection(data)
    source_universe = universe()
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch("operations.services.run_classification", return_value=(data["premium_run"], True)),
        patch(
            "operations.services.build_dashboard_snapshot",
            side_effect=RuntimeError("incompatible"),
        ),
        patch("operations.services.timezone.now", return_value=data["as_of"]),
    ):
        result = run_cycle(collector=Mock(return_value=data["observation"].collection_run))
    assert result.cycle.status == "FAILED_DASHBOARD"
    assert result.cycle.failure_code == "DASHBOARD_BUILD_FAILED"
    assert result.cycle.readiness_assessment is None
    assert result.cycle.operational_events.filter(code="CYCLE_FAILED").count() == 1
