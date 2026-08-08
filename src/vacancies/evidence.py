from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from django.db.models import OuterRef, Subquery

from observations.models import Posting, PostingLifecycleEvent, PostingObservation

from .normalizer import (
    DEDUP_VERSION,
    NORMALIZER_VERSION,
    explicit_redirect_target,
    extract_explicit_requisition,
    normalize_text,
    normalize_url,
)


@dataclass(frozen=True)
class PostingEvidence:
    posting_id: str
    observation_id: str
    source_id: str
    source_posting_id: str
    observed_at: datetime
    first_seen_at: datetime
    lifecycle_status: str
    lifecycle_events: tuple[dict[str, str], ...]
    title: str
    employer: str
    text: str
    location: str
    canonical_url: str
    redirect_target: str | None
    requisition_id: str | None
    requisition_provenance: str | None
    pensum_contract_start: str

    @property
    def normalized_title(self) -> str:
        return normalize_text(self.title)

    @property
    def normalized_employer(self) -> str:
        return normalize_text(self.employer)

    @property
    def normalized_text(self) -> str:
        return normalize_text(self.text)

    @property
    def normalized_location(self) -> str:
        return normalize_text(self.location)

    @property
    def normalized_url(self) -> str:
        return normalize_url(self.canonical_url)


def _payload_text(payload: dict[str, Any], contract: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("description", "responsibilities", "qualifications", "benefits"):
        value = payload.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))
    if not values and contract.get("raw_text"):
        values.append(str(contract["raw_text"]))
    return " ".join(values)


def _lifecycle_evidence(posting: Posting, as_of: datetime) -> tuple[dict[str, str], ...]:
    events = PostingLifecycleEvent.objects.filter(posting=posting, observed_at__lte=as_of).order_by(
        "observed_at", "pk"
    )
    return tuple(
        {
            "id": str(event.pk),
            "event_type": event.event_type,
            "observed_at": event.observed_at.isoformat(),
        }
        for event in events
    )


def select_posting_evidence(as_of: datetime) -> list[PostingEvidence]:
    latest_observation = PostingObservation.objects.filter(
        posting_id=OuterRef("pk"),
        observed_at__lte=as_of,
        observation_status="ACTIVE",
    ).order_by("-observed_at", "-pk")
    postings = (
        Posting.objects.filter(first_seen_at__lte=as_of)
        .annotate(eligible_observation_id=Subquery(latest_observation.values("id")[:1]))
        .exclude(eligible_observation_id=None)
    )
    result: list[PostingEvidence] = []
    for posting in postings.select_related("source"):
        eligible_observation_id = getattr(posting, "eligible_observation_id")
        observation = PostingObservation.objects.get(pk=eligible_observation_id)
        lifecycle_events = _lifecycle_evidence(posting, as_of)
        structured = observation.structured_payload or {}
        contract = observation.contract_payload or {}
        requisition, provenance = extract_explicit_requisition(structured)
        result.append(
            PostingEvidence(
                posting_id=str(posting.pk),
                observation_id=str(observation.pk),
                source_id=posting.source.source_id,
                source_posting_id=posting.source_posting_id,
                observed_at=observation.observed_at,
                first_seen_at=posting.first_seen_at,
                lifecycle_status=(
                    lifecycle_events[-1]["event_type"] if lifecycle_events else "ACTIVE_OBSERVED"
                ),
                lifecycle_events=lifecycle_events,
                title=observation.title,
                employer=str(
                    contract.get("raw_employer") or structured.get("hiring_organization") or ""
                ),
                text=_payload_text(structured, contract),
                location=str(contract.get("raw_location") or structured.get("location_raw") or ""),
                canonical_url=observation.canonical_url,
                redirect_target=explicit_redirect_target(structured),
                requisition_id=requisition,
                requisition_provenance=provenance,
                pensum_contract_start=" ".join(
                    str(structured.get(key) or "")
                    for key in ("pensum", "employment_type", "start_date")
                ).strip(),
            )
        )
    return sorted(result, key=lambda item: item.posting_id)


def input_fingerprint(
    as_of: datetime,
    configuration: dict[str, Any],
    evidence: list[PostingEvidence],
) -> str:
    payload = {
        "dedup_version": DEDUP_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "as_of": as_of.isoformat(),
        "configuration": configuration,
        "inputs": [
            {
                "posting_id": item.posting_id,
                "observation_id": item.observation_id,
                "lifecycle_events": item.lifecycle_events,
            }
            for item in evidence
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def evidence_snapshot(item: PostingEvidence) -> dict[str, Any]:
    value = asdict(item)
    value["observed_at"] = item.observed_at.isoformat()
    value["first_seen_at"] = item.first_seen_at.isoformat()
    return value
