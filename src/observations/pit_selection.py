from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db.models import OuterRef, Subquery

from observations.models import Posting, PostingLifecycleEvent, PostingObservation

PIT_SELECTION_VERSION = "posting-pit-selection-v0.1"


@dataclass(frozen=True)
class SelectedPostingState:
    posting: Posting
    observation: PostingObservation
    lifecycle_event: PostingLifecycleEvent | None

    @property
    def lifecycle_state(self) -> str:
        return self.lifecycle_event.event_type if self.lifecycle_event else "ACTIVE_OBSERVED"


def select_posting_states(as_of: datetime) -> list[SelectedPostingState]:
    """Select content evidence and lifecycle state independently at one PIT cutoff."""
    latest_active = PostingObservation.objects.filter(
        posting_id=OuterRef("pk"),
        observed_at__lte=as_of,
        observation_status="ACTIVE",
    ).order_by("-observed_at", "-pk")
    latest_lifecycle = PostingLifecycleEvent.objects.filter(
        posting_id=OuterRef("pk"),
        observed_at__lte=as_of,
    ).order_by("-observed_at", "-created_at", "-pk")
    postings = list(
        Posting.objects.filter(first_seen_at__lte=as_of)
        .annotate(
            selected_observation_id=Subquery(latest_active.values("id")[:1]),
            selected_lifecycle_event_id=Subquery(latest_lifecycle.values("id")[:1]),
        )
        .exclude(selected_observation_id=None)
        .select_related("source")
        .order_by("pk")
    )
    observations = {
        str(item.pk): item
        for item in PostingObservation.objects.filter(
            pk__in=[getattr(item, "selected_observation_id") for item in postings]
        ).select_related("source", "posting", "collection_run", "raw_artifact")
    }
    lifecycle_events = {
        str(item.pk): item
        for item in PostingLifecycleEvent.objects.filter(
            pk__in=[
                getattr(item, "selected_lifecycle_event_id")
                for item in postings
                if getattr(item, "selected_lifecycle_event_id") is not None
            ]
        ).select_related("posting_observation")
    }
    return [
        SelectedPostingState(
            posting=posting,
            observation=observations[str(getattr(posting, "selected_observation_id"))],
            lifecycle_event=(
                lifecycle_events[str(getattr(posting, "selected_lifecycle_event_id"))]
                if getattr(posting, "selected_lifecycle_event_id") is not None
                else None
            ),
        )
        for posting in postings
    ]
