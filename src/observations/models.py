from __future__ import annotations

import uuid
from typing import Any

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class ImmutablePostingObservationError(RuntimeError):
    pass


class ImmutableGreenRelevanceAssessmentError(RuntimeError):
    pass


class ImmutablePostingLifecycleEventError(RuntimeError):
    pass


class PostingObservationQuerySet(models.QuerySet["PostingObservation"]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutablePostingObservationError("PostingObservation queryset updates are forbidden")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutablePostingObservationError("PostingObservation queryset deletion is forbidden")

    def bulk_update(
        self,
        objs: Any,
        fields: Any,
        batch_size: int | None = None,
    ) -> int:
        raise ImmutablePostingObservationError("PostingObservation bulk updates are forbidden")


class PostingObservationManager(models.Manager["PostingObservation"]):
    def get_queryset(self) -> PostingObservationQuerySet:
        return PostingObservationQuerySet(self.model, using=self._db)

    def bulk_update(
        self,
        objs: Any,
        fields: Any,
        batch_size: int | None = None,
    ) -> int:
        raise ImmutablePostingObservationError("PostingObservation bulk updates are forbidden")


class GreenRelevanceAssessmentQuerySet(models.QuerySet["GreenRelevanceAssessment"]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableGreenRelevanceAssessmentError(
            "GreenRelevanceAssessment queryset updates are forbidden"
        )

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableGreenRelevanceAssessmentError(
            "GreenRelevanceAssessment queryset deletion is forbidden"
        )

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableGreenRelevanceAssessmentError(
            "GreenRelevanceAssessment bulk updates are forbidden"
        )


class GreenRelevanceAssessmentManager(models.Manager["GreenRelevanceAssessment"]):
    def get_queryset(self) -> GreenRelevanceAssessmentQuerySet:
        return GreenRelevanceAssessmentQuerySet(self.model, using=self._db)

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableGreenRelevanceAssessmentError(
            "GreenRelevanceAssessment bulk updates are forbidden"
        )


class PostingLifecycleEventQuerySet(models.QuerySet["PostingLifecycleEvent"]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutablePostingLifecycleEventError("PostingLifecycleEvent updates are forbidden")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutablePostingLifecycleEventError("PostingLifecycleEvent deletion is forbidden")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutablePostingLifecycleEventError(
            "PostingLifecycleEvent bulk updates are forbidden"
        )


class PostingLifecycleEventManager(models.Manager["PostingLifecycleEvent"]):
    def get_queryset(self) -> PostingLifecycleEventQuerySet:
        return PostingLifecycleEventQuerySet(self.model, using=self._db)

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutablePostingLifecycleEventError(
            "PostingLifecycleEvent bulk updates are forbidden"
        )


class CollectionRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    class RunScope(models.TextChoices):
        TARGETED = "TARGETED", "Targeted"
        FULL_SOURCE = "FULL_SOURCE", "Full source"

    class SourceHealthStatus(models.TextChoices):
        HEALTHY = "HEALTHY", "Healthy"
        DEGRADED = "DEGRADED", "Degraded"
        OUTAGE = "OUTAGE", "Outage"
        UNKNOWN = "UNKNOWN", "Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey("sources.Source", on_delete=models.PROTECT)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.RUNNING)
    run_scope = models.CharField(max_length=11, choices=RunScope, default=RunScope.TARGETED)
    snapshot_complete = models.BooleanField(default=False)
    source_health_status = models.CharField(
        max_length=10, choices=SourceHealthStatus, default=SourceHealthStatus.UNKNOWN
    )
    source_health_reason = models.TextField(blank=True)
    listing_url = models.URLField(max_length=500)
    listing_final_url = models.URLField(max_length=500, blank=True)
    listing_http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    listing_raw_artifact = models.OneToOneField(
        "core.RawArtifact",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="listing_collection_run",
    )
    listings_discovered = models.PositiveIntegerField(default=0)
    listing_total_discovered = models.PositiveIntegerField(default=0)
    postings_in_scope = models.PositiveIntegerField(default=0)
    details_fetched = models.PositiveIntegerField(default=0)
    observations_created = models.PositiveIntegerField(default=0)
    green_assessments_created = models.PositiveIntegerField(default=0)
    negative_observations_created = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "collection_run"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["source", "-started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.source.pk}:{self.started_at.isoformat()}"


class Posting(models.Model):
    class LifecycleStatus(models.TextChoices):
        NEW = "NEW", "New"
        STILL_ACTIVE = "STILL_ACTIVE", "Still active"
        DISAPPEARED_PENDING = "DISAPPEARED_PENDING", "Disappeared pending"
        CLOSED_OBSERVED = "CLOSED_OBSERVED", "Closed observed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey("sources.Source", on_delete=models.PROTECT)
    source_posting_id = models.CharField(max_length=100)
    current_status = models.CharField(
        max_length=24, choices=LifecycleStatus, default=LifecycleStatus.NEW
    )
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    first_negative_at = models.DateTimeField(null=True, blank=True)
    last_negative_at = models.DateTimeField(null=True, blank=True)
    closed_observed_at = models.DateTimeField(null=True, blank=True)
    negative_scan_count = models.PositiveIntegerField(default=0)
    latest_canonical_url = models.URLField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "posting"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_posting_id"], name="posting_source_native_id_unique"
            ),
            models.CheckConstraint(
                condition=Q(last_seen_at__gte=F("first_seen_at")), name="posting_seen_dates_ordered"
            ),
            models.CheckConstraint(
                condition=Q(closed_observed_at__isnull=True)
                | Q(closed_observed_at__gte=F("last_seen_at")),
                name="posting_closed_after_last_seen",
            ),
        ]
        indexes = [
            models.Index(fields=["source", "current_status"]),
            models.Index(fields=["last_seen_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.source.pk}:{self.source_posting_id}"


class PostingObservation(models.Model):
    objects = PostingObservationManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection_run = models.ForeignKey(
        CollectionRun, on_delete=models.PROTECT, related_name="observations"
    )
    posting = models.ForeignKey(Posting, on_delete=models.PROTECT, related_name="observations")
    source = models.ForeignKey("sources.Source", on_delete=models.PROTECT)
    observation_status = models.CharField(
        max_length=20,
        choices=[
            ("ACTIVE", "Active"),
            ("NOT_FOUND", "Not found"),
            ("EXPIRED_EXPLICIT", "Expired explicit"),
            ("REDIRECTED", "Redirected"),
            ("BLOCKED", "Blocked"),
            ("ERROR", "Error"),
            ("SOURCE_OUTAGE", "Source outage"),
        ],
        default="ACTIVE",
    )
    source_posting_id = models.CharField(max_length=100)
    observed_at = models.DateTimeField(default=timezone.now)
    canonical_url = models.URLField(max_length=500)
    title = models.CharField(max_length=300)
    date_posted = models.DateField(null=True, blank=True)
    valid_through = models.DateField(null=True, blank=True)
    employment_type = models.CharField(max_length=80, blank=True)
    hiring_organization = models.CharField(max_length=200, blank=True)
    description_html = models.TextField(blank=True)
    responsibilities_html = models.TextField(blank=True)
    qualifications_html = models.TextField(blank=True)
    benefits_html = models.TextField(blank=True)
    location_street = models.CharField(max_length=500, blank=True)
    location_locality = models.CharField(max_length=200, blank=True)
    location_region = models.CharField(max_length=200, blank=True)
    location_postal_code = models.CharField(max_length=100, blank=True)
    location_country = models.CharField(max_length=100, blank=True)
    municipality = models.ForeignKey("reference_data.Municipality", on_delete=models.PROTECT)
    raw_artifact = models.ForeignKey(
        "core.RawArtifact", on_delete=models.PROTECT, related_name="posting_observations"
    )
    structured_payload = models.JSONField()
    contract_payload = models.JSONField()

    class Meta:
        db_table = "posting_observation"
        ordering = ["-observed_at"]
        indexes = [
            models.Index(fields=["source", "source_posting_id", "-observed_at"]),
            models.Index(fields=["date_posted"]),
            models.Index(fields=["valid_through"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["collection_run", "source_posting_id"],
                name="posting_observation_run_source_posting_unique",
            ),
            models.CheckConstraint(
                condition=Q(valid_through__gte=F("date_posted"))
                | Q(date_posted__isnull=True)
                | Q(valid_through__isnull=True),
                name="posting_observation_dates_ordered",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutablePostingObservationError("PostingObservation is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutablePostingObservationError("PostingObservation cannot be deleted")

    def __str__(self) -> str:
        return f"{self.source.pk}:{self.source_posting_id}"


class GreenRelevanceAssessment(models.Model):
    class Result(models.TextChoices):
        GREEN_CONFIRMED = "GREEN_CONFIRMED", "Green confirmed"
        REVIEW = "REVIEW", "Review"
        NOT_GREEN = "NOT_GREEN", "Not green"

    objects = GreenRelevanceAssessmentManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    posting_observation = models.ForeignKey(
        PostingObservation,
        on_delete=models.PROTECT,
        related_name="green_relevance_assessments",
    )
    classifier_version = models.CharField(max_length=80)
    taxonomy_version = models.CharField(max_length=80)
    taxonomy_sha256 = models.CharField(max_length=64)
    result = models.CharField(max_length=20, choices=Result)
    matched_positive_terms = models.JSONField(default=list)
    matched_conditional_terms = models.JSONField(default=list)
    matched_exclusion_terms = models.JSONField(default=list)
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "green_relevance_assessment"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["posting_observation", "classifier_version"],
                name="green_assessment_observation_classifier_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["classifier_version", "result"]),
            models.Index(fields=["taxonomy_sha256"]),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableGreenRelevanceAssessmentError("GreenRelevanceAssessment is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableGreenRelevanceAssessmentError("GreenRelevanceAssessment cannot be deleted")

    def __str__(self) -> str:
        return f"{self.posting_observation.pk}:{self.classifier_version}"


class PostingLifecycleEvent(models.Model):
    class EventType(models.TextChoices):
        NEW = "NEW", "New"
        STILL_ACTIVE = "STILL_ACTIVE", "Still active"
        DISAPPEARED_PENDING = "DISAPPEARED_PENDING", "Disappeared pending"
        CLOSED_OBSERVED = "CLOSED_OBSERVED", "Closed observed"

    objects = PostingLifecycleEventManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    posting = models.ForeignKey(Posting, on_delete=models.PROTECT, related_name="lifecycle_events")
    posting_observation = models.OneToOneField(
        PostingObservation, on_delete=models.PROTECT, related_name="lifecycle_event"
    )
    collection_run = models.ForeignKey(
        CollectionRun, on_delete=models.PROTECT, related_name="lifecycle_events"
    )
    event_type = models.CharField(max_length=24, choices=EventType)
    observed_at = models.DateTimeField()
    source_health_status = models.CharField(max_length=10)
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "posting_lifecycle_event"
        ordering = ["observed_at", "created_at"]
        indexes = [
            models.Index(fields=["posting", "observed_at"]),
            models.Index(fields=["event_type", "observed_at"]),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutablePostingLifecycleEventError("PostingLifecycleEvent is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutablePostingLifecycleEventError("PostingLifecycleEvent cannot be deleted")

    def __str__(self) -> str:
        return f"{self.posting.pk}:{self.event_type}:{self.observed_at.isoformat()}"


class ImmutablePostingLocationResolutionError(RuntimeError):
    pass


class ImmutableGeocoderCacheEntryError(RuntimeError):
    pass


class PostingLocationResolutionQuerySet(models.QuerySet["PostingLocationResolution"]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutablePostingLocationResolutionError("Location resolution updates are forbidden")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutablePostingLocationResolutionError("Location resolution deletion is forbidden")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutablePostingLocationResolutionError("Location bulk updates are forbidden")


class PostingLocationResolutionManager(models.Manager["PostingLocationResolution"]):
    def get_queryset(self) -> PostingLocationResolutionQuerySet:
        return PostingLocationResolutionQuerySet(self.model, using=self._db)

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutablePostingLocationResolutionError("Location bulk updates are forbidden")


class GeocoderCacheEntryQuerySet(models.QuerySet["GeocoderCacheEntry"]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableGeocoderCacheEntryError("Geocoder cache updates are forbidden")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableGeocoderCacheEntryError("Geocoder cache deletion is forbidden")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableGeocoderCacheEntryError("Geocoder cache bulk updates are forbidden")


class GeocoderCacheEntryManager(models.Manager["GeocoderCacheEntry"]):
    def get_queryset(self) -> GeocoderCacheEntryQuerySet:
        return GeocoderCacheEntryQuerySet(self.model, using=self._db)

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableGeocoderCacheEntryError("Geocoder cache bulk updates are forbidden")


class GeocoderCacheEntry(models.Model):
    objects = GeocoderCacheEntryManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=50)
    provider_version = models.CharField(max_length=80)
    normalized_request = models.JSONField()
    request_fingerprint = models.CharField(max_length=64)
    requested_url = models.URLField(max_length=1000)
    final_url = models.URLField(max_length=1000)
    http_status = models.PositiveSmallIntegerField()
    content_type = models.CharField(max_length=255)
    raw_artifact = models.OneToOneField(
        "core.RawArtifact", on_delete=models.PROTECT, related_name="geocoder_cache_entry"
    )
    response_payload = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "geocoder_cache_entry"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_version", "request_fingerprint"],
                name="geocoder_cache_provider_request_unique",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableGeocoderCacheEntryError("GeocoderCacheEntry is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableGeocoderCacheEntryError("GeocoderCacheEntry cannot be deleted")


class PostingLocationResolution(models.Model):
    class ResolutionStatus(models.TextChoices):
        RESOLVED = "RESOLVED", "Resolved"
        REVIEW = "REVIEW", "Review"
        UNRESOLVED = "UNRESOLVED", "Unresolved"

    class LocationPrecision(models.TextChoices):
        EXACT_WORK_ADDRESS = "EXACT_WORK_ADDRESS", "Exact work address"
        POSTCODE = "POSTCODE", "Postcode"
        MUNICIPALITY = "MUNICIPALITY", "Municipality"
        DISTRICT_OR_REGION = "DISTRICT_OR_REGION", "District or region"
        CANTON = "CANTON", "Canton"
        REMOTE_OR_MULTIPLE = "REMOTE_OR_MULTIPLE", "Remote or multiple"
        UNKNOWN = "UNKNOWN", "Unknown"

    class CoordinateSource(models.TextChoices):
        SOURCE_STRUCTURED = "SOURCE_STRUCTURED", "Source structured"
        SOURCE_TEXT_GEOCODED = "SOURCE_TEXT_GEOCODED", "Source text geocoded"
        SWISSTOPO_SEARCHSERVER = "SWISSTOPO_SEARCHSERVER", "swisstopo SearchServer"
        BFS_MUNICIPALITY_CENTROID = "BFS_MUNICIPALITY_CENTROID", "BFS centroid"
        MANUAL_REVIEW = "MANUAL_REVIEW", "Manual review"
        UNKNOWN = "UNKNOWN", "Unknown"

    class PrivacyDisplayLevel(models.TextChoices):
        EXACT_ALLOWED = "EXACT_ALLOWED", "Exact allowed"
        POSTCODE_CENTROID = "POSTCODE_CENTROID", "Postcode centroid"
        MUNICIPALITY_CENTROID = "MUNICIPALITY_CENTROID", "Municipality centroid"
        REGION_CENTROID = "REGION_CENTROID", "Region centroid"
        HIDDEN = "HIDDEN", "Hidden"

    objects = PostingLocationResolutionManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    posting_observation = models.ForeignKey(
        PostingObservation, on_delete=models.PROTECT, related_name="location_resolutions"
    )
    resolver_version = models.CharField(max_length=80)
    resolution_status = models.CharField(max_length=12, choices=ResolutionStatus)
    municipality = models.ForeignKey(
        "reference_data.Municipality",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="posting_location_resolutions",
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_precision = models.CharField(max_length=24, choices=LocationPrecision)
    coordinate_source = models.CharField(max_length=30, choices=CoordinateSource)
    geocoding_confidence = models.FloatField(null=True, blank=True)
    privacy_display_level = models.CharField(max_length=24, choices=PrivacyDisplayLevel)
    public_display_latitude = models.FloatField(null=True, blank=True)
    public_display_longitude = models.FloatField(null=True, blank=True)
    input_fingerprint = models.CharField(max_length=64)
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "posting_location_resolution"
        constraints = [
            models.UniqueConstraint(
                fields=["posting_observation", "resolver_version"],
                name="location_resolution_observation_version_unique",
            ),
            models.CheckConstraint(
                condition=Q(latitude__isnull=True) | (Q(latitude__gte=-90) & Q(latitude__lte=90)),
                name="location_resolution_latitude_valid",
            ),
            models.CheckConstraint(
                condition=Q(longitude__isnull=True)
                | (Q(longitude__gte=-180) & Q(longitude__lte=180)),
                name="location_resolution_longitude_valid",
            ),
            models.CheckConstraint(
                condition=Q(public_display_latitude__isnull=True)
                | (Q(public_display_latitude__gte=-90) & Q(public_display_latitude__lte=90)),
                name="location_resolution_public_lat_valid",
            ),
            models.CheckConstraint(
                condition=Q(public_display_longitude__isnull=True)
                | (Q(public_display_longitude__gte=-180) & Q(public_display_longitude__lte=180)),
                name="location_resolution_public_lon_valid",
            ),
            models.CheckConstraint(
                condition=Q(geocoding_confidence__isnull=True)
                | (Q(geocoding_confidence__gte=0) & Q(geocoding_confidence__lte=1)),
                name="location_resolution_confidence_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(latitude__isnull=True, longitude__isnull=True)
                    | Q(latitude__isnull=False, longitude__isnull=False)
                ),
                name="location_resolution_coordinate_pair",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        public_display_latitude__isnull=True,
                        public_display_longitude__isnull=True,
                    )
                    | Q(
                        public_display_latitude__isnull=False,
                        public_display_longitude__isnull=False,
                    )
                ),
                name="location_resolution_public_coordinate_pair",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(privacy_display_level="HIDDEN")
                    | Q(
                        public_display_latitude__isnull=True,
                        public_display_longitude__isnull=True,
                    )
                ),
                name="location_resolution_hidden_has_no_coordinates",
            ),
        ]
        indexes = [
            models.Index(fields=["resolver_version", "resolution_status"]),
            models.Index(fields=["municipality", "location_precision"]),
            models.Index(fields=["input_fingerprint"]),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutablePostingLocationResolutionError(
                "PostingLocationResolution is append-only"
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutablePostingLocationResolutionError("PostingLocationResolution cannot be deleted")


class GeocodingReviewItem(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RESOLVED = "RESOLVED", "Resolved"
        DISMISSED = "DISMISSED", "Dismissed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    posting_observation = models.ForeignKey(
        PostingObservation, on_delete=models.PROTECT, related_name="geocoding_reviews"
    )
    location_resolution = models.OneToOneField(
        PostingLocationResolution, on_delete=models.PROTECT, related_name="review_item"
    )
    reason = models.CharField(max_length=80)
    candidate_evidence = models.JSONField(default=list)
    resolver_version = models.CharField(max_length=80)
    review_status = models.CharField(
        max_length=12, choices=ReviewStatus, default=ReviewStatus.PENDING
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "geocoding_review_item"
        indexes = [
            models.Index(fields=["review_status", "resolver_version"]),
            models.Index(fields=["reason"]),
        ]
