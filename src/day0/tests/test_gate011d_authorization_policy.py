from __future__ import annotations

import copy
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from dashboard.services import build_dashboard_snapshot
from dashboard.tests.factories import create_dashboard_upstream
from day0.models import Day0AuthorizationPolicy
from day0.policy import (
    AUTHORIZATION_POLICY_VERSION,
    COVERAGE_POLICY_VERSION,
    FRESHNESS_POLICY_VERSION,
    REQUIRED_STRATUM_MINIMA,
)
from day0.services import (
    _evaluate_status,
    _review_evidence,
    _source_plan,
    assess_day0_readiness,
    ensure_authorization_policy,
)
from day0.tests.test_day0 import add_entry, complete_collection, universe
from observations.models import CollectionRun
from sources.models import Source


def final_policy(suffix: str) -> Day0AuthorizationPolicy:
    return Day0AuthorizationPolicy.objects.create(
        policy_version=f"{AUTHORIZATION_POLICY_VERSION}-{suffix}",
        threshold_policy_status="ACCEPTED",
        required_completion_threshold=Decimal("0.8000"),
        freshness_policy_status="ACCEPTED",
        required_source_max_age_hours=72,
        configuration={
            "authorization_policy_version": AUTHORIZATION_POLICY_VERSION,
            "coverage_policy_version": COVERAGE_POLICY_VERSION,
            "freshness_policy_version": FRESHNESS_POLICY_VERSION,
            "stratum_minima": {},
            "minimum_required_source_count": 24,
        },
        input_fingerprint=uuid.uuid4().hex * 2,
    )


def final_universe(data: dict[str, object], policy: Day0AuthorizationPolicy):
    source_universe = universe(accepted=True, threshold=Decimal("0.8"))
    source_universe.policy_version = policy.policy_version
    source_universe._state.adding = True
    source_universe.pk = uuid.uuid4()
    source_universe.input_fingerprint = uuid.uuid4().hex * 2
    source_universe.save(force_insert=True)
    entry = add_entry(source_universe, data["source"])
    return source_universe, entry


@pytest.mark.django_db(transaction=True)
def test_policy_is_fixed_and_versioned_before_state_evaluation() -> None:
    policy = ensure_authorization_policy()

    assert policy.threshold_policy_status == "ACCEPTED"
    assert policy.required_completion_threshold == Decimal("0.8000")
    assert policy.configuration["minimum_required_source_count"] == 24
    assert policy.configuration["coverage_policy_version"] == COVERAGE_POLICY_VERSION
    assert policy.configuration["freshness_policy_version"] == FRESHNESS_POLICY_VERSION
    assert policy.required_source_max_age_hours == 72
    assert policy.configuration["stratum_minima"] == REQUIRED_STRATUM_MINIMA
    assert REQUIRED_STRATUM_MINIMA == {"FEDERAL": 1, "CITY": 4}


@pytest.mark.parametrize(
    ("eligible", "expected"),
    [(23, "DAY_0_NOT_READY"), (24, "DAY_0_AUTHORIZED"), (29, "DAY_0_AUTHORIZED")],
)
def test_exact_coverage_threshold_boundary(eligible: int, expected: str) -> None:
    policy = Day0AuthorizationPolicy(
        policy_version="fixture",
        threshold_policy_status="ACCEPTED",
        freshness_policy_status="ACCEPTED",
        required_completion_threshold=Decimal("0.8000"),
        required_source_max_age_hours=72,
        configuration={},
        input_fingerprint="a" * 64,
    )

    assert _evaluate_status(policy, eligible, 29, 0, 0) == expected


def test_final_policy_authorizes_24_of_29_without_treating_five_blocked_as_vetoes() -> None:
    policy = Day0AuthorizationPolicy(
        policy_version=AUTHORIZATION_POLICY_VERSION,
        threshold_policy_status="ACCEPTED",
        freshness_policy_status="ACCEPTED",
        required_completion_threshold=Decimal("0.8000"),
        required_source_max_age_hours=72,
        configuration={"authorization_policy_version": AUTHORIZATION_POLICY_VERSION},
        input_fingerprint="c" * 64,
    )

    assert _evaluate_status(policy, 24, 29, 0, 5, True, True) == "DAY_0_AUTHORIZED"


def test_structural_rule_can_fail_above_numeric_threshold() -> None:
    policy = Day0AuthorizationPolicy(
        policy_version="fixture",
        threshold_policy_status="ACCEPTED",
        freshness_policy_status="ACCEPTED",
        required_completion_threshold=Decimal("0.8000"),
        required_source_max_age_hours=72,
        configuration={},
        input_fingerprint="b" * 64,
    )

    assert (
        _evaluate_status(policy, 25, 29, 0, 0, True, False)
        == "DAY_0_NOT_READY"
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(hours=71, minutes=59, seconds=59), True),
        (timedelta(hours=72), True),
        (timedelta(hours=72, microseconds=1), False),
    ],
)
def test_source_plan_enforces_exact_freshness_boundary(age: timedelta, expected: bool) -> None:
    data = create_dashboard_upstream(suffix=f"fresh-{age.total_seconds()}")
    complete_collection(data)
    run = data["observation"].collection_run
    run.finished_at = data["as_of"] - age
    run.save(update_fields=["finished_at"])
    policy = final_policy(uuid.uuid4().hex)
    _, entry = final_universe(data, policy)
    assert _source_plan(entry, data["as_of"], policy).freshness_valid is expected


@pytest.mark.django_db(transaction=True)
def test_full_source_itself_must_be_healthy_and_later_activity_controls_current_health() -> None:
    data = create_dashboard_upstream(suffix="health-contract")
    complete_collection(data)
    full = data["observation"].collection_run
    full.source_health_status = "DEGRADED"
    full.save(update_fields=["source_health_status"])
    policy = final_policy(uuid.uuid4().hex)
    _, entry = final_universe(data, policy)
    assert _source_plan(entry, data["as_of"], policy).latest_full_source_run is None

    full.source_health_status = "HEALTHY"
    full.finished_at = data["as_of"] - timedelta(hours=2)
    full.save(update_fields=["source_health_status", "finished_at"])
    targeted = copy.copy(full)
    targeted.pk = uuid.uuid4()
    targeted._state.adding = True
    targeted.run_scope = "TARGETED"
    targeted.snapshot_complete = False
    targeted.finished_at = data["as_of"] - timedelta(hours=1)
    targeted.save(force_insert=True)
    plan = _source_plan(entry, data["as_of"], policy)
    assert plan.latest_full_source_run == full
    assert plan.currently_healthy and plan.freshness_valid

    targeted.source_health_status = "OUTAGE"
    targeted.save(update_fields=["source_health_status"])
    outage_plan = _source_plan(entry, data["as_of"], policy)
    assert outage_plan.freshness_valid is True
    assert not outage_plan.currently_healthy

    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    assessment, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=entry.universe,
        authorization_policy=policy,
    )
    envelope = Client().get(reverse("day0:detail", args=[assessment.pk])).json()
    assert assessment.required_freshness_valid_count == 1
    assert envelope["coverage"]["freshness_valid"] == 1
    assert envelope["coverage"]["eligible"] == 0
    assert envelope["coverage"]["eligible_source_ids"] == []
    assert envelope["market_state"]["green_confirmed_count"] == 0


@pytest.mark.django_db(transaction=True)
def test_final_policy_incomplete_counts_are_diagnostics_not_authorization_failures() -> None:
    data = create_dashboard_upstream(suffix="diagnostic-only-counts")
    complete_collection(data)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    policy = final_policy(uuid.uuid4().hex)
    source_universe, _ = final_universe(data, policy)
    assessment, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
        authorization_policy=policy,
    )
    codes = {item["code"] for item in assessment.blockers}
    envelope = Client().get(reverse("day0:detail", args=[assessment.pk])).json()

    assert "REQUIRED_SOURCE_RUNS_INCOMPLETE" not in codes
    assert "REQUIRED_SOURCE_HEALTH_INCOMPLETE" not in codes
    assert assessment.metrics["required_source_run_coverage"]["numerator"] == 1
    assert assessment.metrics["source_health_coverage"]["numerator"] == 1
    assert all(
        item["code"]
        not in {"REQUIRED_SOURCE_RUNS_INCOMPLETE", "REQUIRED_SOURCE_HEALTH_INCOMPLETE"}
        for item in envelope["authorization_failures"]
    )


@pytest.mark.django_db(transaction=True)
def test_24_of_29_with_five_final_blocked_can_authorize_without_false_failures() -> None:
    data = create_dashboard_upstream(suffix="24-of-29")
    data["source"].source_family = "OFFICIAL_FEDERAL"
    data["source"].save(update_fields=["source_family"])
    complete_collection(data)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    policy = final_policy(uuid.uuid4().hex)
    source_universe, _ = final_universe(data, policy)

    for index in range(23):
        family = "OFFICIAL_MUNICIPAL" if index < 4 else "OFFICIAL_CANTON"
        source = Source.objects.create(
            source_id=f"TEST-DAY0-ELIGIBLE-{index:02d}",
            source_name=f"Eligible source {index}",
            domain=f"eligible-{index}.example",
            source_family=family,
            source_type="PUBLIC_OFFICIAL_EMPLOYER",
            priority="P0",
            coverage_scope="fixture",
            canonicality="CANONICAL",
            platform_family="FIXTURE",
            access_method="HTML",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url=f"https://eligible-{index}.example/jobs",
            search_url=f"https://eligible-{index}.example/jobs",
        )
        add_entry(source_universe, source)
        CollectionRun.objects.create(
            source=source,
            started_at=data["as_of"] - timedelta(hours=1),
            finished_at=data["as_of"] - timedelta(hours=1),
            status="SUCCEEDED",
            run_scope="FULL_SOURCE",
            source_health_status="HEALTHY",
            snapshot_complete=True,
            listing_url=source.search_url,
        )

    for source_id in (
        "SRC-OFF-CANTON-AI",
        "SRC-OFF-CANTON-AG",
        "SRC-OFF-CANTON-BE",
        "SRC-OFF-CANTON-FR",
        "SRC-OFF-CANTON-JU",
    ):
        source = Source.objects.create(
            source_id=source_id,
            source_name=source_id,
            domain=f"{source_id.lower()}.example",
            source_family="OFFICIAL_CANTON",
            source_type="PUBLIC_OFFICIAL_EMPLOYER",
            priority="P0",
            coverage_scope="fixture",
            canonicality="CANONICAL",
            platform_family="BLOCKED",
            access_method="HTML",
            automation_status="BLOCKED",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url=f"https://{source_id.lower()}.example/jobs",
            search_url=f"https://{source_id.lower()}.example/jobs",
        )
        add_entry(source_universe, source)

    assessment, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
        authorization_policy=policy,
    )
    envelope = Client().get(reverse("day0:detail", args=[assessment.pk])).json()

    assert assessment.readiness_status == "DAY_0_AUTHORIZED"
    assert assessment.required_source_count == 29
    assert assessment.required_complete_count == 24
    assert assessment.required_healthy_count == 24
    assert assessment.required_freshness_valid_count == 24
    assert envelope["coverage"]["eligible"] == 24
    assert envelope["authorization_failures"] == []
    assert envelope["reasons"] == []
    assert {item["code"] for item in envelope["diagnostics"]} == {
        "FINAL_BLOCKED_REQUIRED_SOURCES"
    }


@pytest.mark.django_db(transaction=True)
def test_stale_green_record_is_outside_market_and_excluded_review_is_noncritical() -> None:
    data = create_dashboard_upstream(suffix="stale-green")
    complete_collection(data)
    run = data["observation"].collection_run
    run.finished_at = data["as_of"] - timedelta(hours=73)
    run.save(update_fields=["finished_at"])
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    policy = final_policy(uuid.uuid4().hex)
    source_universe, _ = final_universe(data, policy)
    assessment, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
        authorization_policy=policy,
    )
    assert assessment.metrics["day0_market_state"]["green_confirmed_count"] == 0
    assert assessment.active_unique_vacancies == 0

    review = create_dashboard_upstream(
        suffix="excluded-review",
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
    )
    review_snapshot, _ = build_dashboard_snapshot(
        as_of=review["as_of"], dedup_run=review["dedup"], premium_run=review["premium_run"]
    )
    critical, noncritical, critical_green, *_ = _review_evidence(
        review["dedup"], review["premium_run"], review_snapshot, set()
    )
    assert critical_green == 0 and not critical
    assert any(item.startswith("green-excluded-source:") for item in noncritical)


@pytest.mark.django_db(transaction=True)
def test_eligible_green_review_is_authorization_critical() -> None:
    data = create_dashboard_upstream(
        suffix="eligible-review",
        green_result="REVIEW",
        premium_status="SKIPPED_NOT_GREEN",
    )
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    critical, _, critical_green, *_ = _review_evidence(
        data["dedup"], data["premium_run"], snapshot, {str(data["source"].pk)}
    )
    assert critical_green == 1 and critical[0].startswith("green:")


@pytest.mark.django_db(transaction=True)
def test_exact_readiness_and_dashboard_responses_do_not_follow_later_assessment() -> None:
    data = create_dashboard_upstream(suffix="immutable-api")
    complete_collection(data)
    snapshot, _ = build_dashboard_snapshot(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"]
    )
    source_universe = universe()
    add_entry(source_universe, data["source"])
    assessment, _ = assess_day0_readiness(
        as_of=data["as_of"], dedup_run=data["dedup"], premium_run=data["premium_run"],
        dashboard_snapshot=snapshot, source_universe=source_universe,
    )
    client = Client()
    dashboard_before = client.get(reverse("dashboard:snapshot", args=[snapshot.pk])).json()
    exact_before = client.get(reverse("day0:detail", args=[assessment.pk])).json()

    newer = copy.copy(assessment)
    newer.pk = uuid.uuid4()
    newer._state.adding = True
    newer.input_fingerprint = uuid.uuid4().hex * 2
    newer.readiness_status = "DAY_0_AUTHORIZED"
    newer.save(force_insert=True)

    assert client.get(reverse("dashboard:snapshot", args=[snapshot.pk])).json() == dashboard_before
    assert client.get(reverse("day0:detail", args=[assessment.pk])).json() == exact_before
    assert exact_before["assessment_id"] == str(assessment.pk)
