from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import psycopg
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from dashboard.services import build_dashboard_snapshot
from dashboard.tests.factories import create_dashboard_upstream
from day0.tests.test_day0 import add_entry, assess, complete_collection, universe
from observations.models import CollectionRun
from operations.models import ImmutableOperationalEvidenceError, ObservatoryCycle
from operations.services import (
    CycleTimeoutError,
    ObservatoryOperationError,
    _lock_key,
    cycle_summary,
    observatory_status,
    run_cycle,
)
from operations.tests.test_gate012_operations import configuration, cycle, source
from sources.models import Source

pytestmark = pytest.mark.django_db


def _cohort(src: Source) -> SimpleNamespace:
    return SimpleNamespace(universe_version="day0-source-universe-v0.2")


def _healthy_run(src: Source) -> CollectionRun:
    from django.utils import timezone

    now = timezone.now()
    return CollectionRun.objects.create(
        source=src,
        started_at=now,
        finished_at=now,
        status=CollectionRun.Status.SUCCEEDED,
        run_scope=CollectionRun.RunScope.FULL_SOURCE,
        snapshot_complete=True,
        source_health_status=CollectionRun.SourceHealthStatus.HEALTHY,
        listing_url=src.official_url,
        listings_discovered=1,
        listing_total_discovered=1,
        postings_in_scope=1,
        details_fetched=1,
        observations_created=1,
        green_assessments_created=1,
    )


def test_cycle_queryset_and_bulk_mutation_are_forbidden() -> None:
    item = cycle(status="SUCCEEDED_NOT_AUTHORIZED")
    with pytest.raises(ImmutableOperationalEvidenceError):
        ObservatoryCycle.objects.filter(pk=item.pk).update(operational_health="RED")
    with pytest.raises(ImmutableOperationalEvidenceError):
        ObservatoryCycle.objects.filter(pk=item.pk).delete()
    with pytest.raises(ImmutableOperationalEvidenceError):
        ObservatoryCycle.objects.bulk_update([item], ["operational_health"])
    with pytest.raises(ImmutableOperationalEvidenceError):
        item.delete()


@pytest.mark.parametrize(
    "code",
    [
        "RETRY_CONFIGURATION_MISMATCH",
        "RESUME_REQUIRED",
        "RECOVERY_TRIGGER_REQUIRED",
        "ACTIVE_CYCLE_RETRY_REFUSED",
        "RECOVERY_REQUIRES_CYCLE_ID",
        "INVALID_TIMEOUT",
        "BLOCKED_SOURCE_SELECTED",
        "IMPLEMENTED_COHORT_CHANGED",
    ],
)
def test_invalid_operational_states_have_cli_exit_code_9(code: str) -> None:
    with (
        patch(
            "operations.management.commands.run_daily_observatory.run_cycle",
            side_effect=ObservatoryOperationError("cohort", code, "governed refusal"),
        ),
        pytest.raises(CommandError) as caught,
    ):
        call_command("run_daily_observatory", "--json", stdout=StringIO())
    assert caught.value.returncode == 9
    assert code in str(caught.value)


def test_invalid_cycle_uuid_has_cli_exit_code_9() -> None:
    with pytest.raises(CommandError) as caught:
        call_command("run_daily_observatory", "--cycle-id", "not-a-uuid")
    assert caught.value.returncode == 9


def test_dedup_continuity_conflict_is_not_mechanical_dedup_failure() -> None:
    src = source("dedup-continuity")
    collector = Mock(return_value=_healthy_run(src))
    with (
        patch("operations.services.governed_source_cohort", return_value=(_cohort(src), [src])),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch(
            "operations.services.run_deduplication",
            side_effect=ValueError("CONFLICTING_PRIOR_HUMAN_KNOWLEDGE: fixture"),
        ),
    ):
        result = run_cycle(collector=collector)
    item = result.cycle
    assert item.status == ObservatoryCycle.Status.FAILED_CONTINUITY
    assert item.failure_code == "DEDUP_CONTINUITY_FAILED"
    assert item.stage_statuses["dedup_continuity"] == "FAILED"
    assert item.operational_events.filter(code="CONTINUITY_CONFLICT").exists()


def test_mechanical_dedup_failure_retains_exit_5_taxonomy() -> None:
    src = source("dedup-mechanical")
    with (
        patch("operations.services.governed_source_cohort", return_value=(_cohort(src), [src])),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", side_effect=RuntimeError("mechanical")),
    ):
        result = run_cycle(collector=Mock(return_value=_healthy_run(src)))
    assert result.cycle.status == ObservatoryCycle.Status.FAILED_DEDUP
    assert result.cycle.failure_code == "DEDUP_FAILED"
    assert result.cycle.stage_statuses["dedup_continuity"] == "SKIPPED"


def test_timeout_before_first_source_seals_cycle() -> None:
    src = source("timeout-before")
    collector = Mock()
    timeout = CycleTimeoutError("collection", "CYCLE_TIMEOUT", "bounded")
    with (
        patch("operations.services.governed_source_cohort", return_value=(_cohort(src), [src])),
        patch("operations.services._ensure_within_timeout", side_effect=timeout),
    ):
        result = run_cycle(collector=collector)
    assert result.cycle.status == ObservatoryCycle.Status.FAILED_COLLECTION
    assert result.cycle.failure_code == "CYCLE_TIMEOUT"
    assert result.cycle.finished_at is not None
    collector.assert_not_called()


def test_timeout_after_completed_source_preserves_attempt() -> None:
    src = source("timeout-after")
    timeout = CycleTimeoutError("collection", "CYCLE_TIMEOUT", "bounded")
    with (
        patch("operations.services.governed_source_cohort", return_value=(_cohort(src), [src])),
        patch("operations.services._ensure_within_timeout", side_effect=[None, timeout]),
    ):
        result = run_cycle(collector=Mock(return_value=_healthy_run(src)))
    assert result.cycle.status == ObservatoryCycle.Status.FAILED_COLLECTION
    assert result.cycle.source_attempts.count() == 1
    assert result.cycle.source_attempts.get().result == "SUCCEEDED"


def test_timeout_between_collection_and_continuity_is_terminal() -> None:
    src = source("timeout-continuity")
    timeout = CycleTimeoutError("green_continuity", "CYCLE_TIMEOUT", "bounded")
    with (
        patch("operations.services.governed_source_cohort", return_value=(_cohort(src), [src])),
        patch("operations.services._ensure_within_timeout", side_effect=[None, None, timeout]),
    ):
        result = run_cycle(collector=Mock(return_value=_healthy_run(src)))
    assert result.cycle.status == ObservatoryCycle.Status.FAILED_CONTINUITY
    assert result.cycle.stage_statuses["green_continuity"] == "FAILED"


def test_downstream_timeout_is_sealed_at_active_stage() -> None:
    data = create_dashboard_upstream(suffix="ops-timeout-dashboard")
    complete_collection(data)
    source_universe = universe()
    add_entry(source_universe, data["source"])

    def timeout_at_dashboard(*args: object, stage: str, **kwargs: object) -> None:
        if stage == "dashboard":
            raise CycleTimeoutError(stage, "CYCLE_TIMEOUT", "bounded")

    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services._ensure_within_timeout", side_effect=timeout_at_dashboard),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch("operations.services.run_classification", return_value=(data["premium_run"], True)),
    ):
        result = run_cycle(collector=Mock(return_value=data["observation"].collection_run))
    assert result.cycle.status == ObservatoryCycle.Status.FAILED_DASHBOARD
    assert result.cycle.failure_code == "CYCLE_TIMEOUT"
    assert result.cycle.stage_statuses["dashboard"] == "FAILED"


def test_default_status_payload_is_exactly_deterministic() -> None:
    cycle(status="SUCCEEDED_NOT_AUTHORIZED", suffix="deterministic")
    assert observatory_status() == observatory_status()
    assert "volatile_status" not in observatory_status()
    assert "volatile_status" in observatory_status(include_volatile=True)


def test_status_surface_uses_persisted_attempt_and_readiness_evidence() -> None:
    item = cycle(status="SUCCEEDED_NOT_AUTHORIZED", suffix="surface")
    payload = observatory_status()
    surface = payload["latest_cycle"]["status_surface"]
    assert surface["source_cohort_health"]["missing_attempt_evidence"] == item.selected_source_ids
    assert surface["source_cohort_health"]["fresh"] is None
    assert surface["critical_reviews"]["green"] is None
    assert surface["authorization"] is None


def test_blocked_selection_refuses_before_collector_activity() -> None:
    collector = Mock()
    with (
        patch(
            "operations.services.governed_source_cohort",
            side_effect=ObservatoryOperationError(
                "cohort", "BLOCKED_SOURCE_SELECTED", "blocked fixture"
            ),
        ),
        pytest.raises(ObservatoryOperationError, match="blocked fixture"),
    ):
        run_cycle(collector=collector)
    collector.assert_not_called()
    assert ObservatoryCycle.objects.count() == 0


def test_incomplete_source_is_explicit_not_negative_evidence() -> None:
    src = source("incomplete")
    run = _healthy_run(src)
    run.snapshot_complete = False
    run.source_health_status = CollectionRun.SourceHealthStatus.DEGRADED
    run.save()
    with (
        patch("operations.services.governed_source_cohort", return_value=(_cohort(src), [src])),
        patch("operations.services.apply_green_continuity", side_effect=RuntimeError("stop")),
    ):
        result = run_cycle(collector=Mock(return_value=run))
    attempt = result.cycle.source_attempts.get()
    assert attempt.failure_code == "SOURCE_INCOMPLETE_OR_UNHEALTHY"
    assert result.cycle.operational_events.filter(code="SOURCE_INCOMPLETE").exists()
    assert attempt.metrics["negative_observations"] == 0


def test_status_inspection_does_not_synthesize_missed_cycles() -> None:
    cycle(status="SUCCEEDED_NOT_AUTHORIZED", suffix="history-one")
    cycle(status="FAILED_COLLECTION", suffix="history-two")
    before = list(ObservatoryCycle.objects.values_list("pk", flat=True))
    observatory_status()
    assert list(ObservatoryCycle.objects.values_list("pk", flat=True)) == before


@pytest.mark.django_db(transaction=True)
def test_real_postgresql_advisory_lock_refuses_before_collector_activity() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("authoritative advisory-lock contention requires PostgreSQL")
    connection.ensure_connection()
    params = connection.get_connection_params()
    params.pop("cursor_factory", None)
    src = source("postgres-lock")
    collector = Mock()
    with psycopg.connect(**params) as lock_connection:
        with lock_connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [_lock_key()])
        try:
            with patch(
                "operations.services.governed_source_cohort",
                return_value=(_cohort(src), [src]),
            ):
                result = run_cycle(collector=collector)
        finally:
            with lock_connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [_lock_key()])
    assert result.cycle.status == ObservatoryCycle.Status.ABORTED_CONCURRENCY
    assert result.cycle.failure_evidence["http_requests"] == 0
    assert result.cycle.source_attempts.count() == 0
    collector.assert_not_called()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ObservatoryCycle.Status.SUCCEEDED, 0),
        (ObservatoryCycle.Status.SUCCEEDED_NOT_AUTHORIZED, 0),
        (ObservatoryCycle.Status.ABORTED_CONCURRENCY, 2),
        (ObservatoryCycle.Status.FAILED_COLLECTION, 3),
        (ObservatoryCycle.Status.FAILED_COMPLETENESS, 3),
        (ObservatoryCycle.Status.FAILED_CONTINUITY, 4),
        (ObservatoryCycle.Status.FAILED_DEDUP, 5),
        (ObservatoryCycle.Status.FAILED_PREMIUM, 6),
        (ObservatoryCycle.Status.FAILED_DASHBOARD, 7),
        (ObservatoryCycle.Status.FAILED_READINESS, 8),
    ],
)
def test_command_exit_code_matrix(status: str, expected: int) -> None:
    fake_cycle = SimpleNamespace(status=status)
    fake_result = SimpleNamespace(cycle=fake_cycle, reused=False)
    with (
        patch(
            "operations.management.commands.run_daily_observatory.run_cycle",
            return_value=fake_result,
        ),
        patch(
            "operations.management.commands.run_daily_observatory.cycle_summary",
            return_value={"status": status},
        ),
    ):
        if expected:
            with pytest.raises(SystemExit) as caught:
                call_command("run_daily_observatory", "--json", stdout=StringIO())
            assert caught.value.code == expected
        else:
            call_command("run_daily_observatory", "--json", stdout=StringIO())


@pytest.mark.parametrize("expects_alert", [True, False])
def test_authorization_transition_alert_only_on_change(expects_alert: bool) -> None:
    data = create_dashboard_upstream(suffix=f"ops-auth-alert-{expects_alert}")
    complete_collection(data)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    source_universe = universe()
    add_entry(source_universe, data["source"])
    readiness, _ = assess(data, snapshot, source_universe)
    previous_status = "DAY_0_AUTHORIZED" if expects_alert else readiness.readiness_status
    previous = SimpleNamespace(
        readiness_assessment=SimpleNamespace(
            readiness_status=previous_status,
            metrics=readiness.metrics,
        )
    )
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch("operations.services.run_classification", return_value=(data["premium_run"], True)),
        patch("operations.services.build_dashboard_snapshot", return_value=(snapshot, True)),
        patch("operations.services.assess_day0_readiness", return_value=(readiness, True)),
        patch("operations.services._previous_success", return_value=previous),
        patch("operations.services.timezone.now", return_value=data["as_of"]),
    ):
        result = run_cycle(collector=Mock(return_value=data["observation"].collection_run))
    events = result.cycle.operational_events.filter(code="AUTHORIZATION_CHANGED")
    assert events.exists() is expects_alert


def test_dashboard_failure_emits_specific_alert() -> None:
    data = create_dashboard_upstream(suffix="ops-dashboard-alert")
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
        patch("operations.services.build_dashboard_snapshot", side_effect=RuntimeError("bad")),
    ):
        result = run_cycle(collector=Mock(return_value=data["observation"].collection_run))
    assert result.cycle.operational_events.filter(code="DASHBOARD_BUILD_FAILED").exists()


def test_status_surface_uses_governed_eligible_and_pinned_fresh_sources() -> None:
    data = create_dashboard_upstream(suffix="ops-status-evidence")
    complete_collection(data)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    source_universe = universe()
    add_entry(source_universe, data["source"])
    readiness, _ = assess(data, snapshot, source_universe)
    config, fingerprint = configuration("MANUAL", [data["source"]])
    item = ObservatoryCycle.objects.create(
        cycle_version="daily-observatory-cycle-v0.1",
        trigger="MANUAL",
        target_cohort_version="day0-source-universe-v0.2",
        selected_source_ids=[str(data["source"].pk)],
        configuration=config,
        configuration_fingerprint=fingerprint,
        stage_statuses={},
        readiness_assessment=readiness,
    )
    surface = cycle_summary(item)["status_surface"]["source_cohort_health"]
    expected_eligible = sorted(readiness.metrics["day0_market_state"]["eligible_source_ids"])
    assert surface["eligible"] == expected_eligible
    assert surface["fresh"] == [str(data["source"].pk)]


def test_freshness_loss_emits_bounded_alert() -> None:
    data = create_dashboard_upstream(suffix="ops-freshness-alert")
    complete_collection(data)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    source_universe = universe()
    add_entry(source_universe, data["source"])
    readiness, _ = assess(data, snapshot, source_universe)
    readiness.required_freshness_valid_count = 0
    readiness.implemented_required_source_count = 1
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch("operations.services.run_classification", return_value=(data["premium_run"], True)),
        patch("operations.services.build_dashboard_snapshot", return_value=(snapshot, True)),
        patch("operations.services.assess_day0_readiness", return_value=(readiness, True)),
        patch("operations.services.timezone.now", return_value=data["as_of"]),
    ):
        result = run_cycle(collector=Mock(return_value=data["observation"].collection_run))
    event = result.cycle.operational_events.get(code="FRESHNESS_EXPIRED")
    assert event.detail == {"fresh": 0, "implemented": 1}


def test_eligible_source_count_change_uses_governed_market_state() -> None:
    data = create_dashboard_upstream(suffix="ops-eligible-alert")
    complete_collection(data)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    source_universe = universe()
    add_entry(source_universe, data["source"])
    readiness, _ = assess(data, snapshot, source_universe)
    previous = SimpleNamespace(
        readiness_assessment=SimpleNamespace(
            readiness_status=readiness.readiness_status,
            metrics={"day0_market_state": {"eligible_source_ids": []}},
        )
    )
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch("operations.services.run_classification", return_value=(data["premium_run"], True)),
        patch("operations.services.build_dashboard_snapshot", return_value=(snapshot, True)),
        patch("operations.services.assess_day0_readiness", return_value=(readiness, True)),
        patch("operations.services._previous_success", return_value=previous),
        patch("operations.services.timezone.now", return_value=data["as_of"]),
    ):
        result = run_cycle(collector=Mock(return_value=data["observation"].collection_run))
    event = result.cycle.operational_events.get(code="ELIGIBLE_SOURCE_COUNT_CHANGED")
    assert event.detail == {"from": 0, "to": 1}
