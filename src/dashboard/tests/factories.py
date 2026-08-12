from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

from django.utils import timezone

from core.models import RawArtifact
from observations.models import (
    CollectionRun,
    GreenRelevanceAssessment,
    Posting,
    PostingLifecycleEvent,
    PostingLocationResolution,
    PostingObservation,
)
from observations.pit_selection import PIT_SELECTION_VERSION
from premium_segments.classifier import (
    CLASSIFIER_VERSION,
    GREEN_CLASSIFIER_VERSION,
    GREEN_TAXONOMY_VERSION,
    NORMALIZER_VERSION,
    TAXONOMY_VERSION,
    load_taxonomy,
)
from premium_segments.models import PremiumSegmentAssessment, PremiumSegmentRun
from sources.models import Source
from vacancies.models import (
    DedupRun,
    DedupRunPostingAssignment,
    DedupRunVacancyState,
    VacancyPostingMembership,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_dashboard_upstream(
    *,
    green_result: str = "GREEN_CONFIRMED",
    premium_segment: str = "UNKNOWN",
    premium_status: str = "NO_SUFFICIENT_EVIDENCE",
    privacy_context: str = "PUBLIC_OR_NON_RESIDENTIAL",
    location_status: str | None = None,
    location_region: str = "ZH",
    public_coordinates: tuple[float, float] | None = None,
    internal_coordinates: tuple[float, float] | None = None,
    title: str = "Gardener",
    description: str = "<p>Maintain public green spaces</p>",
    canonical_url_status: str = "CANONICAL",
    suffix: str = "1",
    as_of: Any = None,
    vacancy_status: str = "ACTIVE",
    premium_pit_selection_version: str | None = PIT_SELECTION_VERSION,
) -> dict[str, Any]:
    as_of = as_of or timezone.now()
    observed_at = as_of - timedelta(hours=1)
    source = Source.objects.create(
        source_id=f"TEST-DASH-{suffix}",
        source_name=f"Official source {suffix}",
        domain=f"source{suffix}.example",
        source_family="OFFICIAL",
        source_type="PUBLIC_OFFICIAL_EMPLOYER",
        priority="P0",
        coverage_scope="fixture",
        canonicality="CANONICAL",
        platform_family="FIXTURE",
        access_method="HTML",
        automation_status="COLLECTOR_CANDIDATE",
        legal_review_status="APPROVED",
        verification_status="VERIFIED",
        official_url=f"https://source{suffix}.example/jobs",
        search_url=f"https://source{suffix}.example/jobs",
        notes="",
    )
    raw = RawArtifact.objects.create(
        object_key=f"dashboard/{suffix}.json",
        sha256_digest=digest(suffix),
        byte_size=2,
        content_type="application/json",
    )
    collection_run = CollectionRun.objects.create(
        source=source,
        started_at=observed_at,
        finished_at=observed_at,
        status="SUCCEEDED",
        run_scope="TARGETED",
        source_health_status="HEALTHY",
        listing_url=f"https://source{suffix}.example/jobs",
    )
    posting = Posting.objects.create(
        source=source,
        source_posting_id=f"posting-{suffix}",
        current_status="NEW",
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        latest_canonical_url=f"https://source{suffix}.example/job/{suffix}",
    )
    contract = {
        "schema_version": "1.2",
        "source_id": str(source.pk),
        "source_native_id": posting.source_posting_id,
        "observed_at": observed_at.isoformat(),
        "observation_status": "ACTIVE",
        "canonical_url": f"https://source{suffix}.example/job/{suffix}",
        "raw_title": title,
        "raw_payload_sha256": raw.sha256_digest,
        "collector_run_id": str(collection_run.pk),
        "source_health_status": "HEALTHY",
        "source_url": f"https://source{suffix}.example/job/{suffix}",
        "raw_location": "Winterthur",
        "raw_employer": f"Employer {suffix}",
        "published_at_precision": "EXACT_DATE",
        "published_at_parse_method": "SOURCE_FIELD",
    }
    observation = PostingObservation.objects.create(
        collection_run=collection_run,
        posting=posting,
        source=source,
        observation_status="ACTIVE",
        source_posting_id=posting.source_posting_id,
        observed_at=observed_at,
        canonical_url=f"https://source{suffix}.example/job/{suffix}",
        title=title,
        date_posted=observed_at.date(),
        hiring_organization=f"Employer {suffix}",
        description_html=description,
        location_locality="Winterthur",
        location_region=location_region,
        location_country="CH",
        raw_artifact=raw,
        structured_payload={
            "description": description,
            "canonical_url_status": canonical_url_status,
            "pensum": "80-100%",
        },
        contract_payload=contract,
    )
    lifecycle = PostingLifecycleEvent.objects.create(
        posting=posting,
        posting_observation=observation,
        collection_run=collection_run,
        event_type="NEW",
        observed_at=observed_at,
        source_health_status="HEALTHY",
        evidence={"fixture": "dashboard-v0.1"},
    )
    green = GreenRelevanceAssessment.objects.create(
        posting_observation=observation,
        classifier_version=GREEN_CLASSIFIER_VERSION,
        taxonomy_version=GREEN_TAXONOMY_VERSION,
        taxonomy_sha256=digest("green"),
        result=green_result,
        evidence={"fixture": "dashboard-v0.1"},
        created_at=observed_at,
    )
    dedup = DedupRun.objects.create(
        dedup_version="dedup-v0.1",
        normalizer_version="dedup-normalizer-v0.1",
        position_count_version="position-count-v0.1",
        source_precedence_version="source-precedence-v0.1",
        as_of=as_of,
        status="SUCCEEDED",
        started_at=as_of,
        finished_at=as_of,
        postings_considered=1,
        input_fingerprint=digest(f"dedup-{suffix}-{as_of.isoformat()}"),
        configuration={"fixture": "dashboard-v0.1"},
    )
    state = DedupRunVacancyState.objects.create(
        dedup_run=dedup,
        run_vacancy_key=digest(f"state-{suffix}"),
        status=vacancy_status,
        canonical_posting=posting,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        episode_number=1,
    )
    assignment = DedupRunPostingAssignment.objects.create(
        dedup_run=dedup,
        posting=posting,
        run_vacancy_state=state,
        membership_role=VacancyPostingMembership.EvidenceRole.CANONICAL,
        link_method=VacancyPostingMembership.LinkMethod.INITIAL,
    )
    counts = {
        "classified_count": int(premium_status == "CLASSIFIED"),
        "review_count": int(premium_status == "REVIEW"),
        "no_sufficient_evidence_count": int(premium_status == "NO_SUFFICIENT_EVIDENCE"),
        "skipped_not_green_count": int(premium_status == "SKIPPED_NOT_GREEN"),
        "private_residential_standard_count": int(
            premium_segment == "PRIVATE_RESIDENTIAL_STANDARD"
        ),
        "private_residential_premium_count": int(premium_segment == "PRIVATE_RESIDENTIAL_PREMIUM"),
        "private_estate_direct_count": int(premium_segment == "PRIVATE_ESTATE_DIRECT"),
        "unknown_count": int(premium_segment == "UNKNOWN"),
    }
    premium_run = PremiumSegmentRun.objects.create(
        as_of=as_of,
        classifier_version=CLASSIFIER_VERSION,
        normalizer_version=NORMALIZER_VERSION,
        taxonomy_version=TAXONOMY_VERSION,
        taxonomy_sha256=load_taxonomy()[1],
        configuration={
            "fixture": "dashboard-v0.1",
            **(
                {"pit_selection_version": premium_pit_selection_version}
                if premium_pit_selection_version
                else {}
            ),
        },
        input_fingerprint=digest(f"premium-{suffix}-{as_of.isoformat()}"),
        observations_considered=1,
        green_confirmed_eligible=int(green_result == "GREEN_CONFIRMED"),
        status="SUCCEEDED",
        started_at=as_of,
        finished_at=as_of,
        **counts,
    )
    premium = PremiumSegmentAssessment.objects.create(
        run=premium_run,
        posting_observation=observation,
        green_relevance_assessment=green,
        effective_green_result=green_result,
        segment=premium_segment,
        assessment_status=premium_status,
        method="FIXTURE",
        evidence_strength="STRONG" if premium_status == "CLASSIFIED" else "NONE",
        privacy_context=privacy_context,
        evidence={"fixture": "dashboard-v0.1"},
    )
    location = None
    if location_status:
        internal_lat, internal_lon = internal_coordinates or (47.51, 8.72)
        public_lat = public_coordinates[0] if public_coordinates else None
        public_lon = public_coordinates[1] if public_coordinates else None
        location = PostingLocationResolution.objects.create(
            posting_observation=observation,
            resolver_version="geospatial-v0.1",
            privacy_context=privacy_context,
            resolution_status=location_status,
            latitude=internal_lat if location_status == "RESOLVED" else None,
            longitude=internal_lon if location_status == "RESOLVED" else None,
            location_precision="MUNICIPALITY",
            coordinate_source="SOURCE_STRUCTURED",
            privacy_display_level="MUNICIPALITY_CENTROID" if public_coordinates else "HIDDEN",
            public_display_latitude=public_lat,
            public_display_longitude=public_lon,
            input_fingerprint=digest(f"location-{suffix}-{privacy_context}"),
            evidence={"fixture": "dashboard-v0.1"},
            created_at=observed_at,
        )
    return {
        "as_of": as_of,
        "source": source,
        "posting": posting,
        "observation": observation,
        "lifecycle": lifecycle,
        "green": green,
        "dedup": dedup,
        "state": state,
        "assignment": assignment,
        "premium_run": premium_run,
        "premium": premium,
        "location": location,
    }
