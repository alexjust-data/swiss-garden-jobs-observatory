from __future__ import annotations

import copy
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from day0.models import (
    Day0AuthorizationPolicy,
    Day0AuthorizationPolicyDesignation,
    ImmutableDay0EvidenceError,
)
from day0.services import (
    CANONICAL_AUTHORIZATION_POLICY_FINGERPRINT,
    POLICY_AUTHORITY_EFFECTIVE_AT,
    POLICY_AUTHORITY_EVIDENCE,
    POLICY_DESIGNATION_VERSION,
    Day0ContractError,
    _evaluate_status,
    assess_day0_readiness,
    authorization_policy_artifact_fingerprint,
    canonical_authorization_policy_configuration,
    ensure_authorization_policy,
)
from day0.tests.test_day0 import add_entry, assess, universe, upstream

pytestmark = pytest.mark.django_db(transaction=True)

LEGACY_FINGERPRINT = "ce0e3c908a4c07c8ba3f4847c8cc9c84df362534c64db269c4f6b4d37d934230"
CANONICAL_FINGERPRINT = "a72dd56dee6f6a580e1904c4e5427dd3dab9109775fd83722f2108cafb8d294e"


def legacy_configuration() -> dict[str, object]:
    configuration = copy.deepcopy(canonical_authorization_policy_configuration())
    configuration.pop("derived_canton_floor")
    configuration["stratum_minima"] = {"FEDERAL": 1, "CANTON": 15, "CITY": 4}
    freshness = dict(configuration["freshness"])
    freshness["selected_run"] = "latest_causally_available_healthy_complete_FULL_SOURCE"
    configuration["freshness"] = freshness
    return configuration


def create_policy(configuration: dict[str, object]) -> Day0AuthorizationPolicy:
    return Day0AuthorizationPolicy.objects.create(
        policy_version="day0-authorization-v0.1",
        threshold_policy_status="ACCEPTED",
        required_completion_threshold="0.8000",
        freshness_policy_status="ACCEPTED",
        required_source_max_age_hours=72,
        configuration=configuration,
        input_fingerprint=authorization_policy_artifact_fingerprint(configuration),
    )


def designation_for(policy: Day0AuthorizationPolicy) -> Day0AuthorizationPolicyDesignation:
    item = Day0AuthorizationPolicyDesignation(
        designation_version=POLICY_DESIGNATION_VERSION,
        policy_version=policy.policy_version,
        authoritative_policy=policy,
        authority_basis="MERGED_GOVERNANCE_DECISION",
        governance_evidence=POLICY_AUTHORITY_EVIDENCE,
        effective_at=POLICY_AUTHORITY_EFFECTIVE_AT,
    )
    item.input_fingerprint = item.expected_input_fingerprint()
    return item


def test_premerge_fingerprint_reconstructs_exact_database_artifact() -> None:
    legacy = legacy_configuration()
    canonical = canonical_authorization_policy_configuration()

    assert authorization_policy_artifact_fingerprint(legacy) == LEGACY_FINGERPRINT
    assert authorization_policy_artifact_fingerprint(canonical) == CANONICAL_FINGERPRINT
    assert CANONICAL_AUTHORIZATION_POLICY_FINGERPRINT == CANONICAL_FINGERPRINT
    assert legacy["stratum_minima"] == {"FEDERAL": 1, "CANTON": 15, "CITY": 4}
    assert "derived_canton_floor" not in legacy
    assert canonical["stratum_minima"] == {"FEDERAL": 1, "CITY": 4}
    assert canonical["derived_canton_floor"] == 17
    assert legacy != canonical


def test_legacy_artifact_is_preserved_and_final_v01_is_designated() -> None:
    legacy = create_policy(legacy_configuration())
    legacy_snapshot = {
        "id": legacy.pk,
        "configuration": copy.deepcopy(legacy.configuration),
        "fingerprint": legacy.input_fingerprint,
        "created_at": legacy.created_at,
    }

    canonical = ensure_authorization_policy()
    designation = Day0AuthorizationPolicyDesignation.objects.get()

    assert canonical.pk != legacy.pk
    assert canonical.input_fingerprint == CANONICAL_FINGERPRINT
    assert designation.authoritative_policy_id == canonical.pk
    assert designation.designation_version == POLICY_DESIGNATION_VERSION
    assert designation.governance_evidence == POLICY_AUTHORITY_EVIDENCE
    assert designation.effective_at == POLICY_AUTHORITY_EFFECTIVE_AT
    assert designation.governance_evidence["merged_at"] == "2026-08-12T08:09:56Z"
    assert Day0AuthorizationPolicy.objects.filter(policy_version=legacy.policy_version).count() == 2

    legacy.refresh_from_db()
    assert legacy.pk == legacy_snapshot["id"]
    assert legacy.configuration == legacy_snapshot["configuration"]
    assert legacy.input_fingerprint == legacy_snapshot["fingerprint"]
    assert legacy.created_at == legacy_snapshot["created_at"]

    replay = ensure_authorization_policy()
    assert replay.pk == canonical.pk
    assert Day0AuthorizationPolicyDesignation.objects.get().pk == designation.pk


def test_clean_database_creates_only_canonical_artifact_and_reuses_designation() -> None:
    first = ensure_authorization_policy()
    first_designation = Day0AuthorizationPolicyDesignation.objects.get()
    second = ensure_authorization_policy()

    assert first.pk == second.pk
    assert first.input_fingerprint == CANONICAL_FINGERPRINT
    assert Day0AuthorizationPolicy.objects.count() == 1
    assert Day0AuthorizationPolicy.objects.filter(input_fingerprint=LEGACY_FINGERPRINT).count() == 0
    assert Day0AuthorizationPolicyDesignation.objects.get().pk == first_designation.pk


def test_conflicting_existing_designation_fails_closed() -> None:
    legacy = create_policy(legacy_configuration())
    designation_for(legacy).save()

    with pytest.raises(Day0ContractError, match="Conflicting authorization policy"):
        ensure_authorization_policy()

    assert Day0AuthorizationPolicy.objects.count() == 1
    assert Day0AuthorizationPolicyDesignation.objects.get().authoritative_policy_id == legacy.pk


def test_current_code_drift_does_not_replace_existing_authority(monkeypatch) -> None:
    canonical = ensure_authorization_policy()
    designation = Day0AuthorizationPolicyDesignation.objects.get()
    drift = copy.deepcopy(canonical_authorization_policy_configuration())
    drift["derived_canton_floor"] = 18
    monkeypatch.setattr(
        "day0.services.canonical_authorization_policy_configuration",
        lambda: drift,
    )

    with pytest.raises(Day0ContractError, match="does not match merged governance"):
        ensure_authorization_policy()

    assert Day0AuthorizationPolicy.objects.count() == 1
    assert Day0AuthorizationPolicyDesignation.objects.get().pk == designation.pk
    assert designation.authoritative_policy_id == canonical.pk


def test_current_code_drift_cannot_claim_authority_on_clean_database(monkeypatch) -> None:
    drift = copy.deepcopy(canonical_authorization_policy_configuration())
    drift["derived_canton_floor"] = 18
    monkeypatch.setattr(
        "day0.services.canonical_authorization_policy_configuration",
        lambda: drift,
    )

    with pytest.raises(Day0ContractError, match="does not match merged governance"):
        ensure_authorization_policy()

    assert Day0AuthorizationPolicy.objects.count() == 0
    assert Day0AuthorizationPolicyDesignation.objects.count() == 0


def test_final_v01_threshold_and_structural_semantics_are_unchanged() -> None:
    policy = create_policy(canonical_authorization_policy_configuration())

    assert _evaluate_status(policy, 23, 29, 0, 0, True, True) == "DAY_0_NOT_READY"
    assert _evaluate_status(policy, 24, 29, 0, 0, True, True) == "DAY_0_AUTHORIZED"
    assert _evaluate_status(policy, 24, 29, 0, 0, True, False) == "DAY_0_NOT_READY"
    assert policy.configuration["stratum_minima"] == {"FEDERAL": 1, "CITY": 4}
    assert policy.configuration["derived_canton_floor"] == 17


@pytest.mark.parametrize(
    ("cutoff", "available"),
    [
        (datetime(2026, 8, 12, 8, 9, 55, tzinfo=UTC), False),
        (datetime(2026, 8, 12, 8, 9, 56, tzinfo=UTC), True),
    ],
)
def test_designation_authority_boundary_is_inclusive(cutoff: datetime, available: bool) -> None:
    canonical = ensure_authorization_policy()
    data, snapshot = upstream(
        suffix=f"c2-authority-{cutoff.second}",
        as_of=cutoff,
    )
    source_universe = universe(accepted=True, threshold=Decimal("0.8000"))
    add_entry(source_universe, data["source"])

    def assess_at_boundary():
        return assess_day0_readiness(
            as_of=data["as_of"],
            dedup_run=data["dedup"],
            premium_run=data["premium_run"],
            dashboard_snapshot=snapshot,
            source_universe=source_universe,
            authorization_policy=canonical,
        )

    if not available:
        with pytest.raises(Day0ContractError, match="not available at the requested cutoff"):
            assess_at_boundary()
        return

    assessment, reused = assess_at_boundary()
    assert not reused
    assert assessment.as_of == cutoff
    assert assessment.authorization_policy == canonical
    assert Day0AuthorizationPolicyDesignation.objects.get().effective_at == cutoff


@pytest.mark.parametrize(
    ("merged_at", "effective_at", "message"),
    [
        ("not-a-timestamp", POLICY_AUTHORITY_EFFECTIVE_AT, "exact UTC"),
        ("2026-08-12T08:09:56+00:00", POLICY_AUTHORITY_EFFECTIVE_AT, "exact UTC"),
        (
            "2026-08-12T08:09:56Z",
            datetime(2026, 8, 12, 8, 9, 55, tzinfo=UTC),
            "exactly at merged_at",
        ),
    ],
)
def test_merged_governance_time_mismatch_fails_closed(
    merged_at: str, effective_at: datetime, message: str
) -> None:
    policy = create_policy(canonical_authorization_policy_configuration())
    designation = designation_for(policy)
    designation.governance_evidence = {
        **designation.governance_evidence,
        "merged_at": merged_at,
    }
    designation.effective_at = effective_at
    designation.input_fingerprint = designation.expected_input_fingerprint()

    with pytest.raises(ValidationError, match=message):
        designation.save()


def test_merged_governance_time_is_required() -> None:
    policy = create_policy(canonical_authorization_policy_configuration())
    designation = designation_for(policy)
    designation.governance_evidence = dict(designation.governance_evidence)
    designation.governance_evidence.pop("merged_at")
    designation.input_fingerprint = designation.expected_input_fingerprint()

    with pytest.raises(ValidationError, match="merged_at"):
        designation.save()


def test_designation_rejects_forged_fingerprint() -> None:
    policy = create_policy(canonical_authorization_policy_configuration())
    designation = designation_for(policy)
    designation.input_fingerprint = "0" * 64

    with pytest.raises(ValidationError, match="fingerprint"):
        designation.save()


def test_policy_and_designation_are_immutable() -> None:
    policy = create_policy(legacy_configuration())
    designation = designation_for(policy)
    designation.save()

    policy.configuration = {"forged": True}
    with pytest.raises(ImmutableDay0EvidenceError):
        policy.save()
    with pytest.raises(ImmutableDay0EvidenceError):
        policy.delete()

    designation.governance_evidence = {"forged": True}
    with pytest.raises(ImmutableDay0EvidenceError):
        designation.save()
    with pytest.raises(ImmutableDay0EvidenceError):
        designation.delete()


def test_historical_readiness_and_exact_api_remain_pinned_to_legacy_artifact(
    monkeypatch,
) -> None:
    legacy = create_policy(legacy_configuration())
    data, snapshot = upstream(suffix="c2-history")
    source_universe = universe(accepted=True, threshold=Decimal("0.8000"))
    add_entry(source_universe, data["source"])
    with monkeypatch.context() as historical_context:
        historical_context.setattr("day0.services.POLICY_VERSION", "historical-fixture-only")
        historical, _ = assess(data, snapshot, source_universe)
    assert historical.authorization_policy.pk == legacy.pk

    client = Client()
    url = reverse("day0:detail", kwargs={"assessment_id": historical.pk})
    before = client.get(url).json()
    universe_fingerprint = source_universe.input_fingerprint

    canonical = ensure_authorization_policy()
    historical.refresh_from_db()
    source_universe.refresh_from_db()
    after = client.get(url).json()

    assert historical.authorization_policy.pk == legacy.pk
    assert before == after
    assert source_universe.input_fingerprint == universe_fingerprint

    current, _ = assess_day0_readiness(
        as_of=data["as_of"],
        dedup_run=data["dedup"],
        premium_run=data["premium_run"],
        dashboard_snapshot=snapshot,
        source_universe=source_universe,
        authorization_policy=canonical,
    )
    assert current.authorization_policy.pk == canonical.pk
    assert current.pk != historical.pk


def test_new_readiness_rejects_non_authoritative_v01_artifact() -> None:
    legacy = create_policy(legacy_configuration())
    canonical = ensure_authorization_policy()
    data, snapshot = upstream(suffix="c2-reject")
    source_universe = universe(accepted=True, threshold=Decimal("0.8000"))
    add_entry(source_universe, data["source"])

    with pytest.raises(Day0ContractError, match="non-authoritative"):
        assess_day0_readiness(
            as_of=data["as_of"],
            dedup_run=data["dedup"],
            premium_run=data["premium_run"],
            dashboard_snapshot=snapshot,
            source_universe=source_universe,
            authorization_policy=legacy,
        )
    assert canonical.pk == Day0AuthorizationPolicyDesignation.objects.get().authoritative_policy_id
