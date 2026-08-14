from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Protocol
from uuid import UUID

from observations.geospatial import (
    RESOLVER_VERSION,
    GeospatialResolver,
    LocationPrivacyContext,
    ResolutionStats,
    resolution_input_fingerprint,
)
from observations.models import PostingLocationResolution, PostingObservation
from premium_segments.models import PremiumSegmentAssessment, PremiumSegmentRun

BATCH_VERSION = "geospatial-resolution-batch-v0.1"


class GeospatialBatchError(RuntimeError):
    pass


class Resolver(Protocol):
    resolver_version: str
    stats: ResolutionStats

    def resolve(
        self,
        observation: PostingObservation,
        privacy_context: LocationPrivacyContext,
    ) -> PostingLocationResolution: ...


@dataclass(frozen=True)
class GeospatialBatchResult:
    batch_version: str
    premium_run_id: str
    premium_run_fingerprint: str
    premium_run_as_of: str
    dry_run: bool
    selected: int
    already_present: int
    created: int
    resolved: int
    review: int
    unresolved: int
    mappable: int
    hidden: int
    unique_geocoder_requests: int
    cache_hits: int
    network_requests: int
    selected_assessment_ids: tuple[str, ...]
    selected_observation_ids: tuple[str, ...]
    resolution_ids: tuple[str, ...]
    privacy_contexts: dict[str, int]
    resolution_statuses: dict[str, int]
    location_precisions: dict[str, int]
    display_levels: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _targets(run: PremiumSegmentRun) -> list[PremiumSegmentAssessment]:
    targets = list(
        PremiumSegmentAssessment.objects.filter(
            run=run, effective_green_result="GREEN_CONFIRMED"
        )
        .select_related("posting_observation__source", "posting_observation__municipality")
        .order_by("posting_observation_id", "pk")
    )
    contexts: dict[UUID, set[str]] = {}
    for assessment in targets:
        try:
            LocationPrivacyContext(assessment.privacy_context)
        except ValueError as exc:
            raise GeospatialBatchError(
                f"unsupported privacy context for assessment {assessment.pk}"
            ) from exc
        contexts.setdefault(assessment.posting_observation.pk, set()).add(
            assessment.privacy_context
        )
    conflicts = sorted(str(key) for key, values in contexts.items() if len(values) != 1)
    if conflicts:
        raise GeospatialBatchError(
            "conflicting privacy contexts for observations: " + ",".join(conflicts)
        )
    return targets


def resolve_premium_run_locations(
    premium_run_id: UUID | str,
    *,
    dry_run: bool = False,
    resolver: Resolver | None = None,
) -> GeospatialBatchResult:
    try:
        run = PremiumSegmentRun.objects.get(pk=premium_run_id)
    except (PremiumSegmentRun.DoesNotExist, ValueError) as exc:
        raise GeospatialBatchError(f"unknown PremiumSegmentRun: {premium_run_id}") from exc
    if run.status != PremiumSegmentRun.Status.SUCCEEDED:
        raise GeospatialBatchError(f"PremiumSegmentRun {run.pk} is not SUCCEEDED")

    targets = _targets(run)
    selected_assessment_ids = tuple(str(item.pk) for item in targets)
    selected_observation_ids = tuple(str(item.posting_observation.pk) for item in targets)
    privacy_contexts = Counter(item.privacy_context for item in targets)
    active_resolver = resolver
    resolver_version = active_resolver.resolver_version if active_resolver else RESOLVER_VERSION
    if resolver_version != RESOLVER_VERSION:
        raise GeospatialBatchError("resolver version does not match the frozen C2 contract")
    target_fingerprints = {
        (item.posting_observation.pk, item.privacy_context): resolution_input_fingerprint(
            item.posting_observation,
            LocationPrivacyContext(item.privacy_context),
            resolver_version=resolver_version,
        )
        for item in targets
    }
    existing_by_key = {
        (item.posting_observation.pk, item.privacy_context): item
        for item in PostingLocationResolution.objects.filter(
            posting_observation_id__in=[item.posting_observation.pk for item in targets],
            resolver_version=resolver_version,
            privacy_context__in=list(privacy_contexts),
        ).select_related("posting_observation")
    }
    conflicting = sorted(
        f"{observation_id}:{privacy_context}"
        for (observation_id, privacy_context), existing in existing_by_key.items()
        if existing.input_fingerprint
        != target_fingerprints[(observation_id, privacy_context)]
    )
    if conflicting:
        raise GeospatialBatchError(
            "existing location resolution conflicts with current governed input: "
            + ",".join(conflicting)
        )
    already_present = sum(
        (item.posting_observation.pk, item.privacy_context) in existing_by_key
        for item in targets
    )

    resolutions: list[PostingLocationResolution] = []
    before_unique: set[str] = set()
    before_cache_hits = 0
    before_network_requests = 0
    unique_geocoder_requests = 0
    cache_hits = 0
    network_requests = 0
    if not dry_run:
        execution_resolver: Resolver = active_resolver or GeospatialResolver()
        before_unique = set(execution_resolver.stats.unique_geocoder_requests)
        before_cache_hits = execution_resolver.stats.cache_hits
        before_network_requests = execution_resolver.stats.network_requests
        for assessment in targets:
            resolutions.append(
                execution_resolver.resolve(
                    assessment.posting_observation,
                    LocationPrivacyContext(assessment.privacy_context),
                )
            )
        unique_geocoder_requests = len(
            execution_resolver.stats.unique_geocoder_requests - before_unique
        )
        cache_hits = execution_resolver.stats.cache_hits - before_cache_hits
        network_requests = execution_resolver.stats.network_requests - before_network_requests

    statuses = Counter(item.resolution_status for item in resolutions)
    precisions = Counter(item.location_precision for item in resolutions)
    display_levels = Counter(item.privacy_display_level for item in resolutions)
    mappable = sum(
        item.resolution_status == PostingLocationResolution.ResolutionStatus.RESOLVED
        and item.privacy_display_level
        != PostingLocationResolution.PrivacyDisplayLevel.HIDDEN
        and item.public_display_latitude is not None
        and item.public_display_longitude is not None
        for item in resolutions
    )
    return GeospatialBatchResult(
        batch_version=BATCH_VERSION,
        premium_run_id=str(run.pk),
        premium_run_fingerprint=run.input_fingerprint,
        premium_run_as_of=run.as_of.isoformat(),
        dry_run=dry_run,
        selected=len(targets),
        already_present=already_present,
        created=0 if dry_run else len(resolutions) - already_present,
        resolved=statuses[PostingLocationResolution.ResolutionStatus.RESOLVED],
        review=statuses[PostingLocationResolution.ResolutionStatus.REVIEW],
        unresolved=statuses[PostingLocationResolution.ResolutionStatus.UNRESOLVED],
        mappable=mappable,
        hidden=display_levels[PostingLocationResolution.PrivacyDisplayLevel.HIDDEN],
        unique_geocoder_requests=unique_geocoder_requests,
        cache_hits=cache_hits,
        network_requests=network_requests,
        selected_assessment_ids=selected_assessment_ids,
        selected_observation_ids=selected_observation_ids,
        resolution_ids=tuple(str(item.pk) for item in resolutions),
        privacy_contexts=dict(sorted(privacy_contexts.items())),
        resolution_statuses=dict(sorted(statuses.items())),
        location_precisions=dict(sorted(precisions.items())),
        display_levels=dict(sorted(display_levels.items())),
    )
