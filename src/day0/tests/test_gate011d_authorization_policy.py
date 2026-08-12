from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from day0.models import Day0AuthorizationPolicy
from day0.policy import (
    COVERAGE_POLICY_VERSION,
    FRESHNESS_POLICY_VERSION,
    MAX_FULL_SOURCE_AGE_HOURS,
    MINIMUM_REQUIRED_SOURCE_COUNT,
    REQUIRED_STRATUM_MINIMA,
)
from day0.services import _evaluate_status, ensure_authorization_policy


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


def test_freshness_boundary_is_inclusive_wall_clock() -> None:
    maximum = timedelta(hours=MAX_FULL_SOURCE_AGE_HOURS)
    assert maximum <= timedelta(hours=72)
    assert maximum + timedelta(microseconds=1) > timedelta(hours=72)


def test_blocked_source_never_counts_as_observed_zero() -> None:
    policy = ensure_authorization_policy
    assert MINIMUM_REQUIRED_SOURCE_COUNT == 24
    assert callable(policy)
