from __future__ import annotations

from dataclasses import replace
from io import StringIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch
from urllib.error import URLError

import pytest
from django.core.management import call_command
from django.utils import timezone

from dashboard.models import DashboardSnapshot
from dashboard.services import build_dashboard_snapshot
from dashboard.tests.factories import create_dashboard_upstream
from day0.models import Day0ReadinessAssessment
from day0.tests.test_day0 import add_entry, assess, complete_collection, universe
from operations.management.commands.run_daily_observatory import EXIT_BY_STATUS
from operations.models import ObservatoryCycle
from operations.services import (
    CYCLE_VERSION,
    DAILY_GEOSPATIAL_BATCH_VERSION,
    DAILY_GEOSPATIAL_RESOLVER_VERSION,
    STAGE_ORDER,
    CycleTimeoutError,
    ObservatoryOperationError,
    _default_geospatial_runner,
    _sha256,
    cycle_configuration,
    run_cycle,
)
from operations.tests.test_gate012_operations import (
    cycle,
    geospatial_result,
    source,
)

pytestmark = pytest.mark.django_db


def _successful_upstream(
    suffix: str,
) -> tuple[dict[str, Any], DashboardSnapshot, Day0ReadinessAssessment]:
    data = create_dashboard_upstream(suffix=suffix)
    complete_collection(data)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
    )
    source_universe = universe()
    add_entry(source_universe, data["source"])
    readiness, _ = assess(data, snapshot, source_universe)
    return data, snapshot, readiness


def test_v03_configuration_binds_geospatial_v02_order_and_versions() -> None:
    config = cycle_configuration("SCHEDULED", ["B", "A"])
    assert CYCLE_VERSION == "daily-observatory-cycle-v0.3"
    assert config["cycle_version"] == CYCLE_VERSION
    assert list(STAGE_ORDER)[-4:] == ["premium", "geospatial", "dashboard", "readiness"]
    assert config["cutoff_policy"] == "continuity-and-geospatial-available-aligned-pit-v0.2"
    versions = config["versions"]
    assert versions["geospatial_batch"] == "geospatial-resolution-batch-v0.2"
    assert versions["geospatial_resolver"] == "geospatial-v0.2"
    assert versions["location_privacy"] == "location-privacy-v0.1"
    assert versions["geospatial_provider"] == "geo-admin-searchserver-api-2026-08"
    assert versions["raw_lineage"] == "operational-raw-lineage-v0.1"


def test_default_geospatial_runner_pins_promoted_v02_authority() -> None:
    expected = Mock()
    with patch("operations.services.resolve_premium_run_locations", return_value=expected) as batch:
        result = _default_geospatial_runner("00000000-0000-0000-0000-000000000001")

    assert result is expected
    assert DAILY_GEOSPATIAL_BATCH_VERSION == "geospatial-resolution-batch-v0.2"
    assert DAILY_GEOSPATIAL_RESOLVER_VERSION == "geospatial-v0.2"
    assert batch.call_args.kwargs["resolver"].resolver_version == "geospatial-v0.2"


def test_v03_rejects_injected_legacy_geospatial_batch_before_dashboard() -> None:
    data = create_dashboard_upstream(suffix="gate013-legacy-batch")
    complete_collection(data)
    source_universe = universe()
    legacy_result = replace(
        geospatial_result(data["premium_run"]),
        batch_version="geospatial-resolution-batch-v0.1",
    )
    dashboard_builder = Mock()
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch(
            "operations.services.run_classification",
            return_value=(data["premium_run"], True),
        ),
        patch("operations.services.build_dashboard_snapshot", dashboard_builder),
        patch("operations.services.timezone.now", return_value=data["as_of"]),
    ):
        result = run_cycle(
            collector=Mock(return_value=data["observation"].collection_run),
            geospatial_runner=Mock(return_value=legacy_result),
        )
    assert result.cycle.status == ObservatoryCycle.Status.FAILED_GEOSPATIAL
    assert result.cycle.failure_code == "GEOSPATIAL_AUTHORITY_MISMATCH"
    assert result.cycle.stage_statuses["geospatial"] == "FAILED"
    dashboard_builder.assert_not_called()


def test_geospatial_failure_seals_before_dashboard() -> None:
    data = create_dashboard_upstream(suffix="gate013-geospatial-failure")
    complete_collection(data)
    source_universe = universe()
    dashboard_builder = Mock()
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch(
            "operations.services.run_classification",
            return_value=(data["premium_run"], True),
        ),
        patch("operations.services.build_dashboard_snapshot", dashboard_builder),
        patch("operations.services.timezone.now", return_value=data["as_of"]),
    ):
        result = run_cycle(
            collector=Mock(return_value=data["observation"].collection_run),
            geospatial_runner=Mock(side_effect=RuntimeError("provider evidence invalid")),
        )
    assert result.cycle.status == ObservatoryCycle.Status.FAILED_GEOSPATIAL
    assert result.cycle.failure_code == "GEOSPATIAL_FAILED"
    assert result.cycle.stage_statuses["geospatial"] == "FAILED"
    assert result.cycle.stage_statuses["dashboard"] == "PENDING"
    assert result.cycle.dashboard_snapshot is None
    assert result.cycle.operational_events.filter(code="GEOSPATIAL_STAGE_FAILED").count() == 1
    assert result.cycle.operational_events.filter(code="GEOSPATIAL_PROVIDER_DEGRADED").count() == 0
    dashboard_builder.assert_not_called()


def test_new_geospatial_evidence_advances_and_realigns_once() -> None:
    data, snapshot, readiness = _successful_upstream("gate013-realign")
    source_universe = readiness.source_universe
    first = geospatial_result(data["premium_run"], created=1, already_present=0)
    final = geospatial_result(data["premium_run"], created=0, already_present=1)
    geospatial_runner = Mock(side_effect=[first, final])
    dedup_runner = Mock(return_value=(data["dedup"], True))
    premium_runner = Mock(return_value=(data["premium_run"], True))
    dashboard_builder = Mock(return_value=(snapshot, True))
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", dedup_runner),
        patch("operations.services.run_classification", premium_runner),
        patch("operations.services.build_dashboard_snapshot", dashboard_builder),
        patch("operations.services.assess_day0_readiness", return_value=(readiness, True)),
        patch("operations.services.timezone.now", return_value=data["as_of"]),
    ):
        result = run_cycle(
            collector=Mock(return_value=data["observation"].collection_run),
            geospatial_runner=geospatial_runner,
        )
    assert result.cycle.status == ObservatoryCycle.Status.SUCCEEDED_NOT_AUTHORIZED
    assert result.cycle.stage_statuses["geospatial"] == "SUCCEEDED"
    assert dedup_runner.call_count == 2
    assert premium_runner.call_count == 2
    assert geospatial_runner.call_count == 2
    assert (
        dashboard_builder.call_args.kwargs["geospatial_resolver_version"]
        == DAILY_GEOSPATIAL_RESOLVER_VERSION
    )
    assert result.cycle.quality_state["geospatial"]["cutoff_advanced"] is True
    assert result.cycle.quality_state["geospatial"]["created"] == 1
    assert result.cycle.quality_state["geospatial"]["provider_requests"] == 0


def test_second_geospatial_causal_advance_fails_closed() -> None:
    data = create_dashboard_upstream(suffix="gate013-second-advance")
    complete_collection(data)
    source_universe = universe()
    first = geospatial_result(data["premium_run"], created=1, already_present=0)
    second = geospatial_result(data["premium_run"], created=1, already_present=0)
    dashboard_builder = Mock()
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch(
            "operations.services.run_classification",
            return_value=(data["premium_run"], True),
        ),
        patch("operations.services.build_dashboard_snapshot", dashboard_builder),
        patch("operations.services.timezone.now", return_value=data["as_of"]),
    ):
        result = run_cycle(
            collector=Mock(return_value=data["observation"].collection_run),
            geospatial_runner=Mock(side_effect=[first, second]),
        )
    assert result.cycle.status == ObservatoryCycle.Status.FAILED_GEOSPATIAL
    assert result.cycle.failure_code == "GEOSPATIAL_REALIGNMENT_REQUIRES_SECOND_CUTOFF"
    dashboard_builder.assert_not_called()


def test_exact_completed_retry_performs_no_geospatial_activity() -> None:
    item = cycle(status="SUCCEEDED_NOT_AUTHORIZED", suffix="gate013-retry")
    source_item = item.selected_source_ids[0]
    governed = Mock(return_value=(SimpleNamespace(), [SimpleNamespace(pk=source_item)]))
    geospatial_runner = Mock()
    collector = Mock()
    with patch("operations.services.governed_source_cohort", governed):
        result = run_cycle(
            cycle_id=item.pk,
            collector=collector,
            geospatial_runner=geospatial_runner,
        )
    assert result.reused is True
    collector.assert_not_called()
    geospatial_runner.assert_not_called()


@pytest.mark.parametrize(
    ("historical_cycle_version", "resolver_version", "batch_version", "has_geospatial"),
    [
        ("daily-observatory-cycle-v0.1", None, None, False),
        (
            "daily-observatory-cycle-v0.2",
            "geospatial-v0.1",
            "geospatial-resolution-batch-v0.1",
            True,
        ),
    ],
)
def test_completed_historical_cycle_replays_without_current_cohort_or_activity(
    historical_cycle_version: str,
    resolver_version: str | None,
    batch_version: str | None,
    has_geospatial: bool,
) -> None:
    src = source(historical_cycle_version[-4:].replace(".", ""))
    configuration = cycle_configuration("MANUAL", [str(src.pk)])
    configuration["cycle_version"] = historical_cycle_version
    if not has_geospatial:
        configuration["stage_order"] = [
            stage for stage in configuration["stage_order"] if stage != "geospatial"
        ]
        configuration["versions"].pop("geospatial_batch")
        configuration["versions"].pop("geospatial_resolver")
    else:
        configuration["versions"]["geospatial_batch"] = batch_version
        configuration["versions"]["geospatial_resolver"] = resolver_version
    item = ObservatoryCycle.objects.create(
        cycle_version=historical_cycle_version,
        trigger="MANUAL",
        status=ObservatoryCycle.Status.SUCCEEDED_NOT_AUTHORIZED,
        finished_at=timezone.now(),
        target_cohort_version=configuration["target_cohort_version"],
        selected_source_ids=[str(src.pk)],
        configuration=configuration,
        configuration_fingerprint=_sha256(configuration),
        stage_statuses={},
    )
    collector = Mock()
    geospatial_runner = Mock()
    with patch(
        "operations.services.governed_source_cohort",
        side_effect=AssertionError("historical replay consulted current cohort"),
    ):
        result = run_cycle(
            cycle_id=item.pk,
            collector=collector,
            geospatial_runner=geospatial_runner,
        )
    assert result.reused is True
    assert result.cycle.pk == item.pk
    assert result.cycle.configuration_fingerprint == _sha256(configuration)
    collector.assert_not_called()
    geospatial_runner.assert_not_called()


def test_completed_historical_cycle_with_tampered_identity_fails_closed() -> None:
    src = source("historical-tampered")
    configuration = cycle_configuration("MANUAL", [str(src.pk)])
    configuration["cycle_version"] = "daily-observatory-cycle-v0.2"
    # Internally coherent hash, but an impossible v0.2/v0.2 semantic pairing.
    item = ObservatoryCycle.objects.create(
        cycle_version="daily-observatory-cycle-v0.2",
        trigger="MANUAL",
        status=ObservatoryCycle.Status.SUCCEEDED_NOT_AUTHORIZED,
        finished_at=timezone.now(),
        target_cohort_version=configuration["target_cohort_version"],
        selected_source_ids=[str(src.pk)],
        configuration=configuration,
        configuration_fingerprint=_sha256(configuration),
        stage_statuses={},
    )
    with pytest.raises(
        ObservatoryOperationError,
        match="stored identity is inconsistent",
    ):
        run_cycle(cycle_id=item.pk, collector=Mock(), geospatial_runner=Mock())


def test_cli_maps_geospatial_terminal_status_to_exit_10() -> None:
    assert EXIT_BY_STATUS[ObservatoryCycle.Status.FAILED_GEOSPATIAL] == 10
    fake_cycle = SimpleNamespace(status=ObservatoryCycle.Status.FAILED_GEOSPATIAL)
    with (
        patch(
            "operations.management.commands.run_daily_observatory.run_cycle",
            return_value=SimpleNamespace(cycle=fake_cycle, reused=False),
        ),
        patch(
            "operations.management.commands.run_daily_observatory.cycle_summary",
            return_value={"status": "FAILED_GEOSPATIAL"},
        ),
        pytest.raises(SystemExit) as raised,
    ):
        call_command("run_daily_observatory", "--json", stdout=StringIO())
    assert raised.value.code == 10


def test_geospatial_timeout_is_sealed_and_skips_provider_and_dashboard() -> None:
    data = create_dashboard_upstream(suffix="gate013-timeout")
    complete_collection(data)
    source_universe = universe()
    geospatial_runner = Mock()
    dashboard_builder = Mock()

    def timeout_at_geospatial(*args: object, stage: str, **kwargs: object) -> None:
        if stage == "geospatial":
            raise CycleTimeoutError(stage, "CYCLE_TIMEOUT", "bounded")

    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services._ensure_within_timeout", side_effect=timeout_at_geospatial),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch(
            "operations.services.run_classification",
            return_value=(data["premium_run"], True),
        ),
        patch("operations.services.build_dashboard_snapshot", dashboard_builder),
    ):
        result = run_cycle(
            collector=Mock(return_value=data["observation"].collection_run),
            geospatial_runner=geospatial_runner,
        )
    assert result.cycle.status == ObservatoryCycle.Status.FAILED_GEOSPATIAL
    assert result.cycle.failure_code == "CYCLE_TIMEOUT"
    assert result.cycle.stage_statuses["geospatial"] == "FAILED"
    geospatial_runner.assert_not_called()
    dashboard_builder.assert_not_called()


def test_provider_transport_failure_emits_degraded_alert() -> None:
    data = create_dashboard_upstream(suffix="gate013-provider-outage")
    complete_collection(data)
    source_universe = universe()
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(source_universe, [data["source"]]),
        ),
        patch("operations.services.apply_green_continuity", return_value={}),
        patch("operations.services.run_deduplication", return_value=(data["dedup"], True)),
        patch(
            "operations.services.run_classification",
            return_value=(data["premium_run"], True),
        ),
    ):
        result = run_cycle(
            collector=Mock(return_value=data["observation"].collection_run),
            geospatial_runner=Mock(side_effect=URLError("offline")),
        )
    assert result.cycle.status == ObservatoryCycle.Status.FAILED_GEOSPATIAL
    assert result.cycle.operational_events.filter(code="GEOSPATIAL_PROVIDER_DEGRADED").count() == 1


def test_v01_cycle_identity_cannot_resume_as_v03() -> None:
    src = source("gate013-v01")
    old_configuration = cycle_configuration("MANUAL", [str(src.pk)])
    old_configuration["cycle_version"] = "daily-observatory-cycle-v0.1"
    old_configuration["stage_order"] = [
        stage for stage in old_configuration["stage_order"] if stage != "geospatial"
    ]
    item = ObservatoryCycle.objects.create(
        cycle_version="daily-observatory-cycle-v0.1",
        trigger="MANUAL",
        status=ObservatoryCycle.Status.FAILED_COLLECTION,
        finished_at=timezone.now(),
        target_cohort_version="day0-source-universe-v0.2",
        selected_source_ids=[str(src.pk)],
        configuration=old_configuration,
        configuration_fingerprint=_sha256(old_configuration),
        stage_statuses={},
    )
    governed_universe = SimpleNamespace(universe_version=item.target_cohort_version)
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(governed_universe, [src]),
        ),
        pytest.raises(ObservatoryOperationError, match="configuration differs"),
    ):
        run_cycle(
            cycle_id=item.pk,
            trigger="RECOVERY",
            resume=True,
            collector=Mock(),
            geospatial_runner=Mock(),
        )


def test_v02_cycle_identity_cannot_resume_as_v03() -> None:
    src = source("gate013-v02")
    old_configuration = cycle_configuration("MANUAL", [str(src.pk)])
    old_configuration["cycle_version"] = "daily-observatory-cycle-v0.2"
    old_configuration["versions"]["geospatial_batch"] = (
        "geospatial-resolution-batch-v0.1"
    )
    old_configuration["versions"]["geospatial_resolver"] = "geospatial-v0.1"
    item = ObservatoryCycle.objects.create(
        cycle_version="daily-observatory-cycle-v0.2",
        trigger="MANUAL",
        status=ObservatoryCycle.Status.FAILED_GEOSPATIAL,
        finished_at=timezone.now(),
        target_cohort_version="day0-source-universe-v0.2",
        selected_source_ids=[str(src.pk)],
        configuration=old_configuration,
        configuration_fingerprint=_sha256(old_configuration),
        stage_statuses={},
    )
    governed_universe = SimpleNamespace(universe_version=item.target_cohort_version)
    with (
        patch(
            "operations.services.governed_source_cohort",
            return_value=(governed_universe, [src]),
        ),
        pytest.raises(ObservatoryOperationError, match="configuration differs"),
    ):
        run_cycle(
            cycle_id=item.pk,
            trigger="RECOVERY",
            resume=True,
            collector=Mock(),
            geospatial_runner=Mock(),
        )
