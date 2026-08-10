from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, cast
from urllib.parse import urlparse

from django.db import connection, transaction

from observations.geospatial import RESOLVER_VERSION
from observations.models import GreenRelevanceAssessment, PostingLocationResolution
from premium_segments.classifier import CLASSIFIER_VERSION as PREMIUM_CLASSIFIER_VERSION
from premium_segments.classifier import GREEN_CLASSIFIER_VERSION, load_taxonomy
from premium_segments.classifier import NORMALIZER_VERSION as PREMIUM_NORMALIZER_VERSION
from premium_segments.classifier import TAXONOMY_VERSION as PREMIUM_TAXONOMY_VERSION
from premium_segments.models import PremiumSegmentAssessment, PremiumSegmentRun
from vacancies.evidence import select_posting_evidence
from vacancies.models import (
    DedupReviewItem,
    DedupRun,
    DedupRunPostingAssignment,
    DedupRunVacancyState,
)

from .models import DashboardSnapshot, DashboardVacancyRecord

DASHBOARD_VERSION = "dashboard-v0.1"
SOURCE_LINK_POLICY_VERSION = "source-link-v0.1"
SCOPE_NOTICE = (
    "This dashboard contains vacancies observed from the sources currently implemented by "
    "the Swiss Garden Jobs Observatory. It is not yet a complete census of the Swiss "
    "gardening labour market."
)
CONFIGURATION = {
    "public_green_result": "GREEN_CONFIRMED",
    "map_coordinates": "public_display_only",
    "day_zero_authorized": False,
    "source_link_policy": SOURCE_LINK_POLICY_VERSION,
}
PROTECTED_CONTEXTS = {"PRIVATE_RESIDENCE", "CONFIDENTIAL_PRIVATE_RESIDENCE"}
KNOWN_LINK_STATUSES = set(DashboardVacancyRecord.SourceLinkStatus.values)


class DashboardBuildError(RuntimeError):
    pass


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    HIDDEN_TAGS = {
        "script",
        "style",
        "template",
        "noscript",
        "svg",
        "math",
        "iframe",
        "object",
        "embed",
        "foreignobject",
    }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.HIDDEN_TAGS:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.HIDDEN_TAGS and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def visible_text(value: str, limit: int = 6000) -> str:
    parser = _VisibleText()
    parser.feed(value or "")
    rendered = "".join(
        character
        for character in " ".join(parser.parts)
        if not unicodedata.category(character).startswith("C") or character in "\t\r\n"
    )
    return re.sub(r"\s+", " ", rendered).strip()[:limit]


def safe_external_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    raw = value.strip()
    if any(
        character.isspace() or unicodedata.category(character).startswith("C") for character in raw
    ):
        return ""
    try:
        parsed = urlparse(raw)
        hostname = parsed.hostname
        _ = parsed.port
        if hostname:
            hostname.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        return ""
    if parsed.scheme not in {"http", "https"} or not hostname:
        return ""
    if parsed.username or parsed.password or raw.startswith("//"):
        return ""
    return parsed.geturl()


def source_link(observation: Any) -> tuple[str, str, str, str, str]:
    structured = observation.structured_payload or {}
    contract = observation.contract_payload or {}
    explicit = str(structured.get("canonical_url_status") or "").strip().upper()
    canonical = safe_external_url(observation.canonical_url)
    source_url = safe_external_url(contract.get("source_url"))
    if explicit and explicit not in KNOWN_LINK_STATUSES:
        return (
            cast(str, DashboardVacancyRecord.SourceLinkStatus.REVIEW),
            "",
            "",
            "INVALID_EXPLICIT_STATUS",
            source_url,
        )
    if explicit:
        status = explicit
        method = "EXPLICIT_SOURCE_EVIDENCE"
    elif canonical and observation.source.canonicality == "CANONICAL":
        status = cast(str, DashboardVacancyRecord.SourceLinkStatus.CANONICAL)
        method = "CANONICAL_SOURCE_INDIVIDUAL_URL"
    elif source_url:
        status = cast(str, DashboardVacancyRecord.SourceLinkStatus.DISCOVERY_OR_HISTORICAL)
        method = "OBSERVED_SOURCE_FALLBACK"
    elif canonical:
        status = cast(str, DashboardVacancyRecord.SourceLinkStatus.REVIEW)
        method = "UNVERIFIED_CANONICAL_URL"
    else:
        status = cast(str, DashboardVacancyRecord.SourceLinkStatus.NO_LINK_AVAILABLE)
        method = "NO_SAFE_URL"
    labels = {
        "CANONICAL": "Open original advert",
        "AGENCY_CANONICAL": "Open original advert",
        "ORIGINAL_ATS_LINKED": "Open original advert",
        "PORTAL_KNOWN_URL_PENDING": "Open source where published",
        "DISCOVERY_OR_HISTORICAL": "Open observed source",
        "EXPIRED_SOURCE": "Open expired link",
    }
    if status in {"PORTAL_KNOWN_URL_PENDING", "DISCOVERY_OR_HISTORICAL"}:
        selected = source_url or canonical
    else:
        selected = canonical or source_url
    if status in {"NO_LINK_AVAILABLE", "REVIEW"}:
        selected = ""
    return str(status), selected, labels.get(str(status), ""), method, source_url


@dataclass(frozen=True)
class RecordPlan:
    state: DedupRunVacancyState
    values: dict[str, Any]
    fingerprint: dict[str, Any]


def _visibility(assessment: PremiumSegmentAssessment) -> str:
    green = assessment.green_relevance_assessment
    if green is None:
        return cast(str, DashboardVacancyRecord.VisibilityStatus.MISSING_GREEN_ASSESSMENT)
    if green.result == GreenRelevanceAssessment.Result.GREEN_CONFIRMED:
        return cast(str, DashboardVacancyRecord.VisibilityStatus.PUBLIC_GREEN_CONFIRMED)
    if green.result == GreenRelevanceAssessment.Result.NOT_GREEN:
        return cast(str, DashboardVacancyRecord.VisibilityStatus.EXCLUDED_NOT_GREEN)
    return cast(str, DashboardVacancyRecord.VisibilityStatus.REVIEW_NOT_PUBLIC)


def _location(
    assessment: PremiumSegmentAssessment,
    *,
    as_of: datetime,
) -> tuple[PostingLocationResolution | None, str, list[str]]:
    context = assessment.privacy_context
    resolution = (
        PostingLocationResolution.objects.filter(
            posting_observation=assessment.posting_observation,
            resolver_version=RESOLVER_VERSION,
            privacy_context=context,
            created_at__lte=as_of,
        )
        .order_by("-created_at", "-pk")
        .first()
    )
    flags: list[str] = []
    if resolution is None:
        status = (
            cast(str, DashboardVacancyRecord.MappingStatus.PRIVACY_RESOLUTION_MISSING)
            if context in PROTECTED_CONTEXTS
            else cast(str, DashboardVacancyRecord.MappingStatus.LOCATION_UNRESOLVED)
        )
        return None, status, flags
    if resolution.resolution_status == "REVIEW":
        return resolution, cast(str, DashboardVacancyRecord.MappingStatus.LOCATION_REVIEW), flags
    if resolution.resolution_status == "UNRESOLVED":
        return (
            resolution,
            cast(str, DashboardVacancyRecord.MappingStatus.LOCATION_UNRESOLVED),
            flags,
        )
    if resolution.privacy_display_level == "HIDDEN":
        return resolution, cast(str, DashboardVacancyRecord.MappingStatus.LOCATION_HIDDEN), flags
    lat = resolution.public_display_latitude
    lon = resolution.public_display_longitude
    if lat is None or lon is None:
        return (
            resolution,
            cast(str, DashboardVacancyRecord.MappingStatus.PUBLIC_COORDINATES_MISSING),
            flags,
        )
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        flags.append("INVALID_PUBLIC_COORDINATES")
        return (
            resolution,
            cast(str, DashboardVacancyRecord.MappingStatus.PUBLIC_COORDINATES_MISSING),
            flags,
        )
    return resolution, cast(str, DashboardVacancyRecord.MappingStatus.MAPPABLE), flags


def _workload(observation: Any) -> str:
    payload = observation.structured_payload or {}
    value = payload.get("pensum") or payload.get("workload") or ""
    return str(value).strip()[:100] if isinstance(value, str | int | float) else ""


def _source_provenance(state: DedupRunVacancyState) -> list[dict[str, str]]:
    assignments = (
        getattr(state, "posting_assignments")
        .select_related("posting__source")
        .order_by("membership_role", "posting_id")
    )
    return [
        {
            "posting_id": str(item.posting_id),
            "source_posting_id": item.posting.source_posting_id,
            "source_id": str(item.posting.source_id),
            "source_name": item.posting.source.source_name,
            "source_type": item.posting.source.source_type,
            "role": item.membership_role,
        }
        for item in assignments[:20]
    ]


def _record_plans(dedup_run: DedupRun, premium_run: PremiumSegmentRun) -> list[RecordPlan]:
    evidence = {item.posting_id: item for item in select_posting_evidence(dedup_run.as_of)}
    assessments = {
        str(item.posting_observation_id): item
        for item in PremiumSegmentAssessment.objects.filter(run=premium_run).select_related(
            "posting_observation__source",
            "green_relevance_assessment",
        )
    }
    plans: list[RecordPlan] = []
    states = (
        getattr(dedup_run, "vacancy_states")
        .select_related("canonical_posting__source")
        .order_by("run_vacancy_key")
    )
    for state in states:
        selected = evidence.get(str(state.canonical_posting_id))
        if selected is None:
            raise DashboardBuildError(
                f"canonical posting {state.canonical_posting_id} has no PIT observation"
            )
        assessment = assessments.get(selected.observation_id)
        if assessment is None:
            raise DashboardBuildError(
                f"premium run has no assessment for canonical observation {selected.observation_id}"
            )
        observation = assessment.posting_observation
        if observation.posting_id != state.canonical_posting_id:
            raise DashboardBuildError("premium assessment does not belong to canonical posting")
        visibility = _visibility(assessment)
        resolution, mapping, flags = _location(assessment, as_of=dedup_run.as_of)
        if visibility != cast(str, DashboardVacancyRecord.VisibilityStatus.PUBLIC_GREEN_CONFIRMED):
            mapping = cast(str, DashboardVacancyRecord.MappingStatus.LOCATION_UNRESOLVED)
        link_status, selected_url, label, link_method, source_url = source_link(observation)
        contract = observation.contract_payload or {}
        municipality = resolution.municipality if resolution else observation.municipality
        protected = assessment.privacy_context in PROTECTED_CONTEXTS
        provenance = _source_provenance(state)
        values = {
            "dedup_run_vacancy_state": state,
            "run_vacancy_key": state.run_vacancy_key,
            "canonical_posting": state.canonical_posting,
            "canonical_observation": observation,
            "green_assessment": assessment.green_relevance_assessment,
            "premium_assessment": assessment,
            "location_resolution": resolution,
            "visibility_status": visibility,
            "mapping_status": mapping,
            "source_link_status": link_status,
            "selected_external_url": selected_url,
            "visible_link_label": label,
            "link_selection_method": link_method,
            "title": visible_text(observation.title, 300),
            "employer": visible_text(observation.hiring_organization, 300),
            "safe_description": "" if protected else visible_text(observation.description_html),
            "vacancy_status": state.status,
            "municipality_name": municipality.municipality_name if municipality else "",
            "canton_code": municipality.canton_code
            if municipality
            else observation.location_region,
            "source_published_date": observation.date_posted,
            "published_at_precision": str(contract.get("published_at_precision") or "UNKNOWN"),
            "published_at_parse_method": str(
                contract.get("published_at_parse_method") or "MISSING"
            ),
            "first_seen_at": state.first_seen_at,
            "last_seen_at": state.last_seen_at,
            "closed_observed_at": state.closed_observed_at,
            "location_precision": resolution.location_precision if resolution else "UNKNOWN",
            "privacy_context": assessment.privacy_context,
            "privacy_display_level": (
                resolution.privacy_display_level if resolution else "HIDDEN" if protected else ""
            ),
            "location_resolution_status": (resolution.resolution_status if resolution else ""),
            "public_display_latitude": (
                resolution.public_display_latitude
                if resolution is not None
                and mapping == cast(str, DashboardVacancyRecord.MappingStatus.MAPPABLE)
                else None
            ),
            "public_display_longitude": (
                resolution.public_display_longitude
                if resolution is not None
                and mapping == cast(str, DashboardVacancyRecord.MappingStatus.MAPPABLE)
                else None
            ),
            "premium_segment": assessment.segment,
            "premium_assessment_status": assessment.assessment_status,
            "source_name": observation.source.source_name,
            "source_type": observation.source.source_type,
            "canonical_url": safe_external_url(observation.canonical_url),
            "source_url": source_url,
            "workload": _workload(observation),
            "positions_count": state.positions_count,
            "multi_hire_possible": state.multi_hire_possible,
            "episode_number": state.episode_number,
            "source_provenance": provenance,
            "quality_flags": flags,
        }
        plans.append(
            RecordPlan(
                state,
                values,
                {
                    "state_id": str(state.pk),
                    "observation_id": str(observation.pk),
                    "green_assessment_id": str(assessment.green_relevance_assessment_id or ""),
                    "premium_assessment_id": str(assessment.pk),
                    "location_resolution_id": str(resolution.pk) if resolution else None,
                    "location_available_at": (
                        resolution.created_at.isoformat() if resolution else None
                    ),
                    "assignments": provenance,
                    "presentation": {
                        key: (
                            value.isoformat()
                            if hasattr(value, "isoformat")
                            else str(value.pk)
                            if hasattr(value, "pk")
                            else value
                        )
                        for key, value in values.items()
                        if key
                        not in {
                            "dedup_run_vacancy_state",
                            "canonical_posting",
                            "canonical_observation",
                            "green_assessment",
                            "premium_assessment",
                            "location_resolution",
                        }
                    },
                },
            )
        )
    return plans


def _fingerprint(
    dedup_run: DedupRun, premium_run: PremiumSegmentRun, plans: list[RecordPlan]
) -> str:
    payload = {
        "dashboard_version": DASHBOARD_VERSION,
        "as_of": dedup_run.as_of.isoformat(),
        "dedup_run": str(dedup_run.pk),
        "premium_run": str(premium_run.pk),
        "configuration": CONFIGURATION,
        "records": [plan.fingerprint for plan in plans],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _lock(fingerprint: str) -> None:
    if connection.vendor == "postgresql":
        key = int.from_bytes(bytes.fromhex(fingerprint)[:8], "big", signed=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _validate_runs(dedup_run: DedupRun, premium_run: PremiumSegmentRun, as_of: datetime) -> None:
    if dedup_run.status != DedupRun.Status.SUCCEEDED:
        raise DashboardBuildError("dedup run must be SUCCEEDED")
    if premium_run.status != PremiumSegmentRun.Status.SUCCEEDED:
        raise DashboardBuildError("premium run must be SUCCEEDED")
    if dedup_run.as_of != as_of or premium_run.as_of != as_of:
        raise DashboardBuildError("dashboard, dedup and premium as_of values must match exactly")
    if dedup_run.dedup_version != "dedup-v0.1":
        raise DashboardBuildError("unsupported dedup version")
    if premium_run.classifier_version != PREMIUM_CLASSIFIER_VERSION:
        raise DashboardBuildError("unsupported premium classifier version")
    if premium_run.normalizer_version != PREMIUM_NORMALIZER_VERSION:
        raise DashboardBuildError("unsupported premium normalizer version")
    if premium_run.taxonomy_version != PREMIUM_TAXONOMY_VERSION:
        raise DashboardBuildError("unsupported premium taxonomy version")
    _, expected_taxonomy_sha256 = load_taxonomy()
    if premium_run.taxonomy_sha256 != expected_taxonomy_sha256:
        raise DashboardBuildError("unsupported premium taxonomy hash")

    assigned_posting_ids = {
        str(value)
        for value in DedupRunPostingAssignment.objects.filter(dedup_run=dedup_run).values_list(
            "posting_id", flat=True
        )
    }
    expected_observations = {
        item.observation_id
        for item in select_posting_evidence(as_of)
        if item.posting_id in assigned_posting_ids
    }
    actual_observations = {
        str(value)
        for value in PremiumSegmentAssessment.objects.filter(run=premium_run).values_list(
            "posting_observation_id", flat=True
        )
    }
    if expected_observations != actual_observations:
        raise DashboardBuildError("dedup and premium evidence universes are incompatible")
    if (
        PremiumSegmentAssessment.objects.filter(run=premium_run)
        .exclude(green_relevance_assessment__isnull=True)
        .exclude(green_relevance_assessment__classifier_version=GREEN_CLASSIFIER_VERSION)
        .exists()
    ):
        raise DashboardBuildError("premium run uses an incompatible green classifier")


@transaction.atomic
def build_dashboard_snapshot(
    *, as_of: datetime, dedup_run: DedupRun, premium_run: PremiumSegmentRun
) -> tuple[DashboardSnapshot, bool]:
    _validate_runs(dedup_run, premium_run, as_of)
    plans = _record_plans(dedup_run, premium_run)
    fingerprint = _fingerprint(dedup_run, premium_run, plans)
    _lock(fingerprint)
    existing = DashboardSnapshot.objects.filter(
        dashboard_version=DASHBOARD_VERSION,
        as_of=as_of,
        input_fingerprint=fingerprint,
    ).first()
    if existing:
        return existing, True
    public = [
        plan
        for plan in plans
        if plan.values["visibility_status"]
        == cast(str, DashboardVacancyRecord.VisibilityStatus.PUBLIC_GREEN_CONFIRMED)
    ]
    excluded = [
        plan
        for plan in plans
        if plan.values["visibility_status"]
        == cast(str, DashboardVacancyRecord.VisibilityStatus.EXCLUDED_NOT_GREEN)
    ]
    public_ids = {id(item) for item in public}
    excluded_ids = {id(item) for item in excluded}
    review = [plan for plan in plans if id(plan) not in public_ids | excluded_ids]
    mappable = [
        plan
        for plan in public
        if plan.values["mapping_status"] == cast(str, DashboardVacancyRecord.MappingStatus.MAPPABLE)
    ]
    resolutions = [plan.values["location_resolution"] for plan in plans]
    snapshot = DashboardSnapshot.objects.create(
        dashboard_version=DASHBOARD_VERSION,
        as_of=as_of,
        dedup_run=dedup_run,
        premium_run=premium_run,
        dedup_version=dedup_run.dedup_version,
        premium_classifier_version=premium_run.classifier_version,
        green_classifier_version=GREEN_CLASSIFIER_VERSION,
        geospatial_resolver_version=RESOLVER_VERSION,
        source_link_policy_version=SOURCE_LINK_POLICY_VERSION,
        configuration=CONFIGURATION,
        input_fingerprint=fingerprint,
        total_vacancy_states=len(plans),
        public_green_eligible_count=len(public),
        excluded_not_green_count=len(excluded),
        review_not_public_count=len(review),
        mappable_vacancy_count=len(mappable),
        unmappable_vacancy_count=len(public) - len(mappable),
        known_publication_date_count=sum(
            bool(plan.values["source_published_date"]) for plan in public
        ),
        unknown_publication_date_count=sum(
            not plan.values["source_published_date"] for plan in public
        ),
        geospatial_resolved_count=sum(
            item is not None and item.resolution_status == "RESOLVED" for item in resolutions
        ),
        geospatial_review_count=sum(
            item is not None and item.resolution_status == "REVIEW" for item in resolutions
        ),
        geospatial_unresolved_count=sum(
            item is None or item.resolution_status == "UNRESOLVED" for item in resolutions
        ),
        private_location_protected_count=sum(
            plan.values["privacy_context"] in PROTECTED_CONTEXTS for plan in plans
        ),
        dedup_review_count=DedupReviewItem.objects.filter(
            algorithm_decision__dedup_run=dedup_run,
            status=DedupReviewItem.Status.PENDING,
        ).count(),
    )
    records = [DashboardVacancyRecord(snapshot=snapshot, **plan.values) for plan in plans]
    for record in records:
        record.clean()
        record.validate_constraints()
    DashboardVacancyRecord.objects.bulk_create(records)
    if snapshot.vacancy_records.count() != snapshot.total_vacancy_states:
        raise DashboardBuildError("dashboard record coverage is incomplete")
    return snapshot, False
