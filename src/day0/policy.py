from __future__ import annotations

from dataclasses import dataclass

from reference_data.models import Municipality
from sources.models import Source

SOURCE_UNIVERSE_VERSION = "day0-source-universe-v0.2"
AUTHORIZATION_POLICY_VERSION = "day0-authorization-v0.1"
COVERAGE_POLICY_VERSION = "day0-coverage-v0.1"
FRESHNESS_POLICY_VERSION = "full-source-freshness-v0.1"
READINESS_VERSION = "day0-readiness-v0.3"

REQUIRED_SOURCE_COUNT = 29
MINIMUM_REQUIRED_SOURCE_COUNT = 24
MINIMUM_REQUIRED_SOURCE_COVERAGE = "0.8000"
MAX_FULL_SOURCE_AGE_HOURS = 72

REQUIRED_STRATUM_MINIMA: dict[str, int] = {
    "FEDERAL": 1,
    "CITY": 4,
}
DERIVED_CANTON_FLOOR = 17

# GATE-011C-6 closed all provisional research states. These are governance
# evidence, not mutable registry fields and not runtime source-model enums.
FINAL_BLOCKED_REQUIRED_SOURCES: dict[str, str] = {
    "SRC-OFF-CANTON-AI": "SEMANTIC_IDENTITY_BLOCKED",
    "SRC-OFF-CANTON-AG": "POLICY_BLOCKED",
    "SRC-OFF-CANTON-BE": "MULTI_SURFACE_BLOCKED",
    "SRC-OFF-CANTON-FR": "MULTI_SURFACE_BLOCKED",
    "SRC-OFF-CANTON-JU": "SOURCE_UNIVERSE_BLOCKED",
    "SRC-OFF-CANTON-NW": "SEMANTIC_IDENTITY_BLOCKED",
    "SRC-OFF-CANTON-OW": "POLICY_BLOCKED",
    "SRC-OFF-CANTON-UR": "TECHNICAL_RELIABILITY_BLOCKED",
    "SRC-OFF-CANTON-VS": "MULTI_SURFACE_BLOCKED",
}

# The registry has no structured canton code. This is the only identity-specific
# mapping in v0.2 and every key is reconciled against the frozen registry in tests.
CANTON_SOURCE_CODES: dict[str, str] = {
    "SRC-OFF-CANTON-AG": "AG",
    "SRC-OFF-CANTON-AI": "AI",
    "SRC-OFF-CANTON-AR": "AR",
    "SRC-OFF-CANTON-BE": "BE",
    "SRC-OFF-CANTON-BL": "BL",
    "SRC-OFF-CANTON-BS": "BS",
    "SRC-OFF-CANTON-FR": "FR",
    "SRC-OFF-CANTON-GL": "GL",
    "SRC-OFF-CANTON-GR": "GR",
    "SRC-OFF-CANTON-JU": "JU",
    "SRC-OFF-CANTON-LU": "LU",
    "SRC-OFF-CANTON-NW": "NW",
    "SRC-OFF-CANTON-OW": "OW",
    "SRC-OFF-CANTON-SG": "SG",
    "SRC-OFF-CANTON-SH": "SH",
    "SRC-OFF-CANTON-SO": "SO",
    "SRC-OFF-CANTON-SZ": "SZ",
    "SRC-OFF-CANTON-TG": "TG",
    "SRC-OFF-CANTON-UR": "UR",
    "SRC-OFF-CANTON-VS": "VS",
    "SRC-OFF-CANTON-ZG": "ZG",
    "SRC-OFF-CANTON-ZH": "ZH",
}

NON_VACANCY_FAMILIES = frozenset({"OFFICIAL_REFERENCE", "OFFICIAL_STATISTICS", "SALARY_REFERENCE"})
VACANCY_CANONICALITY_VALUES = frozenset({"CANONICAL", "HIGH_CANONICALITY", "AGENCY_CANONICAL"})
KNOWN_AUTOMATION_STATUSES = frozenset(
    {
        "COLLECTOR_CANDIDATE",
        "FEED_OR_TERMS_RESEARCH_REQUIRED",
        "DATA_ACCESS_RESEARCH_REQUIRED",
        "READY_FOR_IMPLEMENTATION",
        "ACCESS_METHOD_RESEARCH_REQUIRED",
        "DO_NOT_IMPLEMENT_AS_BULK_READER",
        "METHOD_RESEARCH_REQUIRED",
        "REFERENCE_INGEST_CANDIDATE",
        "NETWORK_MAPPING_REQUIRED",
        "DIRECTORY_RESEARCH_REQUIRED",
    }
)
KNOWN_LEGAL_STATUSES = frozenset(
    {
        "AUTOMATION_REVIEW_REQUIRED",
        "TERMS_REVIEW_REQUIRED",
        "PUBLIC_DATA_DOCUMENTED",
        "TERMS_AND_ACCESS_REVIEW_REQUIRED",
        "ACCESS_SCOPE_MUST_BE_CONFIRMED",
        "PUBLIC_REFERENCE_REVIEW",
    }
)


class SourcePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class SourcePolicyDecision:
    classification: str
    target_role: str
    access_status: str
    reason: str
    access_reason: str
    canton_code: str | None = None


def _has_german_municipality(canton_code: str) -> bool:
    return Municipality.objects.filter(canton_code=canton_code).exists()


def _is_not_applicable(source: Source) -> bool:
    return source.source_family in NON_VACANCY_FAMILIES or source.source_type == "PUBLISHING_API"


def access_status_for(source: Source, *, not_applicable: bool) -> tuple[str, str]:
    if not_applicable:
        return "NOT_APPLICABLE", "Source is not a vacancy-collection surface."
    if source.automation_status not in KNOWN_AUTOMATION_STATUSES:
        raise SourcePolicyError(
            f"Unknown automation_status for governed source {source.source_id}."
        )
    if source.legal_review_status not in KNOWN_LEGAL_STATUSES:
        raise SourcePolicyError(
            f"Unknown legal_review_status for governed source {source.source_id}."
        )
    if (
        source.automation_status == "READY_FOR_IMPLEMENTATION"
        and source.legal_review_status == "PUBLIC_DATA_DOCUMENTED"
    ):
        return "READY_FOR_IMPLEMENTATION", "Automation and public-data review are explicit."
    return (
        "BLOCKED_PENDING_ACCESS_REVIEW",
        (
            "Automation/access/legal authorization is not jointly complete; "
            "verification alone is insufficient."
        ),
    )


def classify_source(source: Source) -> SourcePolicyDecision:
    not_applicable = _is_not_applicable(source)
    access_status, access_reason = access_status_for(source, not_applicable=not_applicable)
    if not_applicable:
        return SourcePolicyDecision(
            "NOT_APPLICABLE",
            "NONE",
            access_status,
            "Reference, statistics, salary, or publishing-only source; not a vacancy read surface.",
            access_reason,
        )

    canton_code = CANTON_SOURCE_CODES.get(source.source_id)
    if canton_code is not None:
        if not _has_german_municipality(canton_code):
            raise SourcePolicyError(
                f"Canton source {source.source_id} has no municipality in the "
                "governed German-language universe."
            )
        return SourcePolicyDecision(
            "DAY0_REQUIRED",
            "REQUIRED",
            access_status,
            "Official canton portal covers at least one governed German-language municipality.",
            access_reason,
            canton_code,
        )

    if (
        source.source_family == "OFFICIAL_FEDERAL"
        and source.priority == "P0"
        and source.canonicality in VACANCY_CANONICALITY_VALUES
    ):
        return SourcePolicyDecision(
            "DAY0_REQUIRED",
            "REQUIRED",
            access_status,
            "Canonical federal direct-employer vacancy portal.",
            access_reason,
        )

    if source.source_family == "OFFICIAL_MUNICIPAL" and source.priority == "P0":
        if "green unit" in source.coverage_scope.casefold():
            return SourcePolicyDecision(
                "DAY0_SUPPORTING",
                "SUPPORTING",
                access_status,
                "P0 municipal green-unit surface supports its parent municipal portal.",
                access_reason,
            )
        return SourcePolicyDecision(
            "DAY0_REQUIRED",
            "REQUIRED",
            access_status,
            "P0 canonical central municipal vacancy portal.",
            access_reason,
        )

    if source.source_id == "SRC-OFF-JOBROOM":
        return SourcePolicyDecision(
            "DAY0_SUPPORTING",
            "SUPPORTING",
            access_status,
            (
                "Official public discovery surface; not a canonical direct-employer "
                "denominator source."
            ),
            access_reason,
        )

    if source.priority == "P1":
        return SourcePolicyDecision(
            "DAY0_SUPPORTING",
            "SUPPORTING",
            access_status,
            (
                "P1 vacancy source supplies sector/private-market support outside the "
                "required canonical cohort."
            ),
            access_reason,
        )

    return SourcePolicyDecision(
        "DEFERRED",
        "NONE",
        access_status,
        "Employment source is outside the minimum Day-0 required/supporting cohort.",
        access_reason,
    )


def assert_policy_ids_exist() -> None:
    registry_ids = set(Source.objects.values_list("source_id", flat=True))
    missing = sorted(set(CANTON_SOURCE_CODES) - registry_ids)
    if missing:
        raise SourcePolicyError(f"Day-0 policy references unknown frozen source IDs: {missing}")
