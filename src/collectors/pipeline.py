from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from collectors.adapters import get_adapter
from collectors.governed_http import GovernedHttpClient, ensure_default_endpoints
from collectors.platforms import (
    FetchedPage,
    FetchRequest,
    ListingEntry,
    ParsedSourcePosting,
    PlatformAdapter,
)
from core.hashing import sha256_file, sha256_hex
from core.models import RawArtifact
from core.storage import RawObjectStore
from observations.contracts import validate_posting_observation_contract
from observations.green_relevance import (
    CLASSIFIER_VERSION,
    TAXONOMY_VERSION,
    GreenRelevanceClassifier,
)
from observations.lifecycle import get_or_create_posting, record_active, record_healthy_absences
from observations.models import (
    CollectionRun,
    CollectionRunFetch,
    GreenRelevanceAssessment,
    PostingObservation,
)
from reference_data.models import Municipality
from sources.models import Source


class CollectionPipelineError(RuntimeError):
    pass


class SourceGovernanceError(CollectionPipelineError):
    pass


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchedPage: ...


def enforce_source_policy(source: Source, *, acknowledge_automation_review: bool) -> None:
    if source.automation_status != "COLLECTOR_CANDIDATE":
        raise SourceGovernanceError(
            f"source automation_status {source.automation_status!r} blocks collection"
        )
    if source.legal_review_status == "APPROVED":
        return
    if source.legal_review_status == "AUTOMATION_REVIEW_REQUIRED" and acknowledge_automation_review:
        return
    if source.legal_review_status == "AUTOMATION_REVIEW_REQUIRED":
        raise SourceGovernanceError("source requires --acknowledge-automation-review")
    raise SourceGovernanceError(
        f"source legal_review_status {source.legal_review_status!r} blocks collection"
    )


def resolve_municipality(parsed: ParsedSourcePosting) -> Municipality | None:
    locality = parsed.location_locality.strip()
    region = parsed.location_region.strip().upper()
    if not locality:
        return None
    candidates = Municipality.objects.filter(municipality_name__iexact=locality)
    if region:
        candidates = candidates.filter(canton_code=region)
    matches = list(candidates[:2])
    return matches[0] if len(matches) == 1 else None


def publication_confidence(parsed: ParsedSourcePosting) -> float | None:
    if not parsed.published_at_raw:
        return None
    if parsed.published_at_precision == "EXACT_DATE":
        return 1.0 if parsed.date_posted is not None else None
    if parsed.published_at_precision in {"EXACT_DATETIME", "RELATIVE_RESOLVED"}:
        return 1.0 if parsed.source_published_at is not None else None
    return None


def build_contract_payload(
    *,
    parsed: ParsedSourcePosting,
    page: FetchedPage,
    raw_artifact: RawArtifact,
    source: Source,
    municipality: Municipality | None,
    run: CollectionRun,
    observed_at: datetime,
) -> dict[str, object]:
    normalized = None
    if municipality is not None:
        normalized = {
            "bfs_code": municipality.pk,
            "municipality": municipality.municipality_name,
            "canton_code": municipality.canton_code,
            "location_precision": "MUNICIPALITY",
        }
    combined_text = "\n".join(
        part
        for part in (
            parsed.description_html,
            parsed.responsibilities_html,
            parsed.qualifications_html,
            parsed.benefits_html,
        )
        if part
    )
    raw_text = parsed.contract_raw_text if parsed.contract_raw_text is not None else combined_text
    return {
        "schema_version": "1.2",
        "source_id": str(source.pk),
        "source_native_id": parsed.source_posting_id,
        "observed_at": observed_at.isoformat(),
        "observation_status": "ACTIVE",
        "source_url": page.requested_url,
        "canonical_url": parsed.canonical_url,
        "http_status": page.status_code,
        "raw_title": parsed.title,
        "raw_location": parsed.raw_location or None,
        "raw_employer": parsed.hiring_organization or None,
        "raw_text": raw_text or None,
        "raw_payload_sha256": raw_artifact.sha256_digest,
        "published_at_raw": parsed.published_at_raw,
        "source_published_at": parsed.source_published_at.isoformat()
        if parsed.source_published_at
        else None,
        "source_updated_at": parsed.source_updated_at.isoformat()
        if parsed.source_updated_at
        else None,
        "published_at_precision": parsed.published_at_precision,
        "published_at_parse_method": parsed.published_at_parse_method,
        "published_at_confidence": publication_confidence(parsed),
        "collector_run_id": str(run.pk),
        "source_health_status": "HEALTHY",
        "normalized_location": normalized,
    }


class SharedCollectionPipeline:
    def __init__(
        self,
        *,
        source_id: str,
        adapter: PlatformAdapter | None = None,
        fetcher: Fetcher | None = None,
        raw_store: RawObjectStore | None = None,
        delay_seconds: float = 1.0,
        clock: Callable[[], datetime] = timezone.now,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be nonnegative")
        self.source = Source.objects.get(source_id=source_id)
        ensure_default_endpoints(self.source)
        self.adapter = adapter or get_adapter(self.source)
        if self.adapter.platform_family != self.source.platform_family:
            raise SourceGovernanceError("adapter platform family does not match source registry")
        self.fetcher = fetcher or GovernedHttpClient(self.source)
        self.raw_store = raw_store or RawObjectStore(settings.CORE_RAW_OBJECT_STORE_PATH)
        self.delay_seconds = delay_seconds
        self.clock = clock
        self.classifier = GreenRelevanceClassifier()

    def _fetch(self, request: FetchRequest) -> FetchedPage:
        fetch_request = getattr(self.fetcher, "fetch_request", None)
        return fetch_request(request) if fetch_request else self.fetcher.fetch(request.url)

    def collect(
        self,
        *,
        posting_ids: set[str] | None = None,
        limit: int | None = None,
        full_snapshot: bool = False,
        acknowledge_automation_review: bool = False,
    ) -> CollectionRun:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        if full_snapshot and (posting_ids or limit is not None):
            raise ValueError("full_snapshot is incompatible with posting_ids/limit")
        if not full_snapshot and not posting_ids:
            raise ValueError("TARGETED collection requires at least one posting_id")
        enforce_source_policy(
            self.source, acknowledge_automation_review=acknowledge_automation_review
        )
        started_at = self.clock()
        first_request = self.adapter.initial_listing_request(self.source)
        run = CollectionRun.objects.create(
            source=self.source,
            listing_url=first_request.url,
            run_scope=(
                CollectionRun.RunScope.FULL_SOURCE
                if full_snapshot
                else CollectionRun.RunScope.TARGETED
            ),
            started_at=started_at,
        )
        stage, current_id = "listing", "listing"
        discovered: dict[str, ListingEntry] = {}
        observed_ids: set[str] = set()
        assessed_ids: set[str] = set()
        try:
            request: FetchRequest | None = first_request
            ordinal = 0
            total_reported: int | None = None
            discovery_complete = False
            while request is not None:
                page = self._fetch(request)
                artifact = self._persist_raw(
                    run, request.role.lower(), str(ordinal), page, self.clock()
                )
                CollectionRunFetch.objects.create(
                    collection_run=run,
                    fetch_role=request.role,
                    ordinal=ordinal,
                    requested_url=page.requested_url,
                    final_url=page.final_url,
                    http_status=page.status_code,
                    content_type=page.content_type,
                    raw_artifact=artifact,
                    evidence={
                        "request_method": request.method.upper(),
                        "form_data": list(request.form_data),
                        "surface_name": request.context.get("surface_name"),
                    },
                )
                if ordinal == 0:
                    run.listing_final_url = page.final_url
                    run.listing_http_status = page.status_code
                    run.listing_raw_artifact = artifact
                parsed_page = self.adapter.parse_listing_page(page, request, self.source)
                for entry in parsed_page.entries:
                    previous = discovered.get(entry.source_posting_id)
                    if previous and previous.detail_url != entry.detail_url:
                        raise CollectionPipelineError(
                            f"duplicate ID {entry.source_posting_id} has conflicting detail URLs"
                        )
                    discovered.setdefault(entry.source_posting_id, entry)
                total_reported = parsed_page.total_reported or total_reported
                discovery_complete = parsed_page.discovery_complete
                request = parsed_page.next_request
                ordinal += 1
            if not discovery_complete:
                raise CollectionPipelineError(
                    "adapter did not prove listing discovery completeness"
                )
            if total_reported is not None and len(discovered) != total_reported:
                raise CollectionPipelineError(
                    f"reported total {total_reported} differs from unique IDs {len(discovered)}"
                )
            run.listings_discovered = len(discovered)
            run.listing_total_discovered = len(discovered)
            entries = list(discovered.values())
            if posting_ids:
                missing = posting_ids - set(discovered)
                if missing:
                    raise CollectionPipelineError(
                        f"requested postings are not active: {sorted(missing)}"
                    )
                entries = [entry for entry in entries if entry.source_posting_id in posting_ids]
            if limit is not None:
                entries = entries[:limit]
            scoped_ids = {entry.source_posting_id for entry in entries}
            run.postings_in_scope = len(scoped_ids)
            stage = "details"
            for index, entry in enumerate(entries):
                current_id = entry.source_posting_id
                if index and self.delay_seconds:
                    time.sleep(self.delay_seconds)
                observed_at = self.clock()
                detail_request = self.adapter.detail_request(entry, self.source)
                page = self._fetch(detail_request)
                artifact = self._persist_raw(run, "detail", current_id, page, observed_at)
                CollectionRunFetch.objects.create(
                    collection_run=run,
                    fetch_role="DETAIL",
                    ordinal=index,
                    requested_url=page.requested_url,
                    final_url=page.final_url,
                    http_status=page.status_code,
                    content_type=page.content_type,
                    raw_artifact=artifact,
                    evidence={
                        "source_posting_id": current_id,
                        "request_method": detail_request.method.upper(),
                        "surface_name": detail_request.context.get("surface_name")
                        or entry.listing_metadata.get("surface_name"),
                    },
                )
                run.details_fetched += 1
                parsed = self.adapter.parse_detail(page, entry, self.source)
                if parsed.source_posting_id != current_id:
                    raise CollectionPipelineError("adapter changed source posting identity")
                municipality = resolve_municipality(parsed)
                contract = build_contract_payload(
                    parsed=parsed,
                    page=page,
                    raw_artifact=artifact,
                    source=self.source,
                    municipality=municipality,
                    run=run,
                    observed_at=observed_at,
                )
                validate_posting_observation_contract(contract)
                with transaction.atomic():
                    posting, created = get_or_create_posting(
                        source=self.source,
                        source_posting_id=current_id,
                        observed_at=observed_at,
                        canonical_url=parsed.canonical_url,
                    )
                    observation = PostingObservation.objects.create(
                        collection_run=run,
                        posting=posting,
                        source=self.source,
                        observation_status="ACTIVE",
                        source_posting_id=current_id,
                        observed_at=observed_at,
                        canonical_url=parsed.canonical_url,
                        title=parsed.title,
                        date_posted=parsed.date_posted,
                        valid_through=parsed.valid_through,
                        employment_type=parsed.employment_type,
                        hiring_organization=parsed.hiring_organization,
                        description_html=parsed.description_html,
                        responsibilities_html=parsed.responsibilities_html,
                        qualifications_html=parsed.qualifications_html,
                        benefits_html=parsed.benefits_html,
                        location_street=parsed.location_street,
                        location_locality=parsed.location_locality,
                        location_region=parsed.location_region,
                        location_postal_code=parsed.location_postal_code,
                        location_country=parsed.location_country,
                        municipality=municipality,
                        raw_artifact=artifact,
                        structured_payload=parsed.structured_payload,
                        contract_payload=contract,
                    )
                    decision = self.classifier.classify_observation(observation)
                    GreenRelevanceAssessment.objects.create(
                        posting_observation=observation,
                        classifier_version=CLASSIFIER_VERSION,
                        taxonomy_version=TAXONOMY_VERSION,
                        taxonomy_sha256=self.classifier.taxonomy_sha256,
                        result=decision.result,
                        matched_positive_terms=decision.matched_positive_terms,
                        matched_conditional_terms=decision.matched_conditional_terms,
                        matched_exclusion_terms=decision.matched_exclusion_terms,
                        evidence=decision.evidence,
                    )
                    record_active(
                        posting=posting,
                        observation=observation,
                        run=run,
                        observed_at=observed_at,
                        created=created,
                    )
                observed_ids.add(current_id)
                assessed_ids.add(current_id)
                run.observations_created += 1
                run.green_assessments_created += 1
            counts_equal = (
                run.postings_in_scope
                == run.details_fetched
                == run.observations_created
                == run.green_assessments_created
            )
            sets_equal = scoped_ids == observed_ids == assessed_ids
            if full_snapshot and not (counts_equal and sets_equal):
                raise CollectionPipelineError("FULL_SOURCE count or posting-ID set mismatch")
            run.source_health_status = CollectionRun.SourceHealthStatus.HEALTHY
            run.source_health_reason = "COMPLETE_VALIDATED_SCOPE"
            if full_snapshot:
                stage = "lifecycle"
                with transaction.atomic():
                    run.save()
                    run.negative_observations_created = record_healthy_absences(
                        run=run, active_ids=scoped_ids, observed_at=self.clock()
                    )
            run.status = CollectionRun.Status.SUCCEEDED
            run.snapshot_complete = full_snapshot and counts_equal and sets_equal
            run.finished_at = self.clock()
            run.save()
            return run
        except Exception as exc:
            run.status = CollectionRun.Status.FAILED
            run.snapshot_complete = False
            run.source_health_status = (
                CollectionRun.SourceHealthStatus.OUTAGE
                if stage == "listing"
                else CollectionRun.SourceHealthStatus.DEGRADED
            )
            run.source_health_reason = f"{stage.upper()}_FAILURE"
            run.finished_at = self.clock()
            run.error_message = f"posting {current_id}: {exc}"
            run.save()
            raise

    def _persist_raw(
        self,
        run: CollectionRun,
        kind: str,
        identifier: str,
        page: FetchedPage,
        observed_at: datetime,
    ) -> RawArtifact:
        digest = sha256_hex(page.body)
        safe_source = re.sub(r"[^a-z0-9_-]+", "-", str(self.source.pk).casefold())
        object_key = (
            f"sources/{safe_source}/{observed_at:%Y/%m/%d}/{run.pk}/"
            f"{kind}-{identifier}-{digest[:16]}"
        )
        path: Path = self.raw_store.write_bytes(object_key, page.body)
        if sha256_file(path) != digest:
            raise CollectionPipelineError(f"RAW SHA-256 verification failed for {object_key}")
        return RawArtifact.objects.create(
            object_key=object_key,
            sha256_digest=digest,
            byte_size=len(page.body),
            content_type=page.content_type,
        )


def collect_source(
    source_id: str,
    *,
    posting_ids: set[str] | None = None,
    limit: int | None = None,
    full_snapshot: bool = False,
    acknowledge_automation_review: bool = False,
) -> CollectionRun:
    return SharedCollectionPipeline(source_id=source_id).collect(
        posting_ids=posting_ids,
        limit=limit,
        full_snapshot=full_snapshot,
        acknowledge_automation_review=acknowledge_automation_review,
    )
