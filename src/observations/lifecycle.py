from __future__ import annotations

from datetime import datetime, timedelta

from observations.contracts import validate_posting_observation_contract
from observations.models import CollectionRun, Posting, PostingLifecycleEvent, PostingObservation
from sources.models import Source

CLOSURE_CONFIRMATION_DELAY = timedelta(hours=48)


def get_or_create_posting(
    *, source: Source, source_posting_id: str, observed_at: datetime, canonical_url: str
) -> tuple[Posting, bool]:
    try:
        return Posting.objects.select_for_update().get(
            source=source, source_posting_id=source_posting_id
        ), False
    except Posting.DoesNotExist:
        return Posting.objects.create(
            source=source,
            source_posting_id=source_posting_id,
            current_status=Posting.LifecycleStatus.NEW,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            latest_canonical_url=canonical_url,
        ), True


def record_active(
    *,
    posting: Posting,
    observation: PostingObservation,
    run: CollectionRun,
    observed_at: datetime,
    created: bool,
) -> None:
    previous_status = posting.current_status
    event_type = (
        PostingLifecycleEvent.EventType.NEW
        if created
        else PostingLifecycleEvent.EventType.STILL_ACTIVE
    )
    posting.last_seen_at = observed_at
    posting.latest_canonical_url = observation.canonical_url
    posting.current_status = (
        Posting.LifecycleStatus.NEW if created else Posting.LifecycleStatus.STILL_ACTIVE
    )
    posting.first_negative_at = None
    posting.last_negative_at = None
    posting.closed_observed_at = None
    posting.negative_scan_count = 0
    posting.save()
    PostingLifecycleEvent.objects.create(
        posting=posting,
        posting_observation=observation,
        collection_run=run,
        event_type=event_type,
        observed_at=observed_at,
        source_health_status=CollectionRun.SourceHealthStatus.HEALTHY,
        evidence={
            "previous_status": previous_status,
            "transition": event_type,
            "reason": "FIRST_OBSERVATION" if created else "ACTIVE_OBSERVATION",
        },
    )


def _not_found_contract(
    *, posting: Posting, latest: PostingObservation, run: CollectionRun, observed_at: datetime
) -> dict[str, object]:
    artifact = run.listing_raw_artifact
    if artifact is None:
        raise ValueError("healthy negative scan requires listing RAW evidence")
    return {
        "schema_version": "1.2",
        "source_id": str(run.source.pk),
        "source_native_id": posting.source_posting_id,
        "observed_at": observed_at.isoformat(),
        "observation_status": "NOT_FOUND",
        "source_url": latest.canonical_url,
        "canonical_url": latest.canonical_url,
        "http_status": 200,
        "raw_title": latest.title,
        "raw_location": None,
        "raw_employer": None,
        "raw_text": None,
        "raw_payload_sha256": artifact.sha256_digest,
        "published_at_raw": None,
        "source_published_at": None,
        "source_updated_at": None,
        "published_at_precision": "UNKNOWN",
        "published_at_parse_method": "MISSING",
        "published_at_confidence": None,
        "collector_run_id": str(run.pk),
        "source_health_status": "HEALTHY",
        "normalized_location": None,
    }


def record_healthy_absences(
    *, run: CollectionRun, active_ids: set[str], observed_at: datetime
) -> int:
    if run.run_scope != CollectionRun.RunScope.FULL_SOURCE:
        return 0
    if run.source_health_status != CollectionRun.SourceHealthStatus.HEALTHY:
        raise ValueError("negative lifecycle transitions require a healthy source run")
    count = 0
    candidates = (
        Posting.objects.select_for_update()
        .filter(source=run.source)
        .exclude(source_posting_id__in=active_ids)
        .exclude(current_status=Posting.LifecycleStatus.CLOSED_OBSERVED)
    )
    for posting in candidates:
        latest = (
            PostingObservation.objects.filter(posting=posting, observation_status="ACTIVE")
            .order_by("-observed_at")
            .first()
        )
        if latest is None:
            continue
        contract = _not_found_contract(
            posting=posting, latest=latest, run=run, observed_at=observed_at
        )
        validate_posting_observation_contract(contract)
        artifact = run.listing_raw_artifact
        if artifact is None:
            raise ValueError("listing RAW disappeared during lifecycle processing")
        negative_number = posting.negative_scan_count + 1
        first_negative = posting.first_negative_at or observed_at
        separation = observed_at - first_negative
        closes = posting.negative_scan_count >= 1 and separation >= CLOSURE_CONFIRMATION_DELAY
        event_type = (
            PostingLifecycleEvent.EventType.CLOSED_OBSERVED
            if closes
            else PostingLifecycleEvent.EventType.DISAPPEARED_PENDING
        )
        observation = PostingObservation.objects.create(
            collection_run=run,
            posting=posting,
            source=run.source,
            observation_status="NOT_FOUND",
            source_posting_id=posting.source_posting_id,
            observed_at=observed_at,
            canonical_url=latest.canonical_url,
            title=latest.title,
            municipality=latest.municipality,
            raw_artifact=artifact,
            structured_payload={},
            contract_payload=contract,
        )
        posting.current_status = (
            Posting.LifecycleStatus.CLOSED_OBSERVED
            if closes
            else Posting.LifecycleStatus.DISAPPEARED_PENDING
        )
        posting.first_negative_at = first_negative
        posting.last_negative_at = observed_at
        posting.closed_observed_at = observed_at if closes else None
        posting.negative_scan_count = negative_number
        posting.save()
        PostingLifecycleEvent.objects.create(
            posting=posting,
            posting_observation=observation,
            collection_run=run,
            event_type=event_type,
            observed_at=observed_at,
            source_health_status=CollectionRun.SourceHealthStatus.HEALTHY,
            evidence={
                "observation_status": "NOT_FOUND",
                "negative_scan_number": negative_number,
                "first_negative_at": first_negative.isoformat(),
                "separation_seconds": separation.total_seconds(),
                "closure_rule": "TWO_HEALTHY_NEGATIVES_SEPARATED_BY_AT_LEAST_48_HOURS",
            },
        )
        count += 1
    return count
