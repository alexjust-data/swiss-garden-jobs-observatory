from __future__ import annotations

import math
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class ImmutableDashboardEvidenceError(RuntimeError):
    pass


class DashboardEvidenceQuerySet(models.QuerySet[Any]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableDashboardEvidenceError("dashboard evidence is append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableDashboardEvidenceError("dashboard evidence cannot be deleted")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableDashboardEvidenceError("dashboard evidence is append-only")


class DashboardEvidenceManager(models.Manager[Any]):
    def get_queryset(self) -> DashboardEvidenceQuerySet:
        return DashboardEvidenceQuerySet(self.model, using=self._db)

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableDashboardEvidenceError("dashboard evidence is append-only")


class AppendOnlyDashboardEvidence(models.Model):
    objects = DashboardEvidenceManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableDashboardEvidenceError("dashboard evidence is append-only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableDashboardEvidenceError("dashboard evidence cannot be deleted")


class DashboardSnapshot(AppendOnlyDashboardEvidence):
    vacancy_records: models.Manager[DashboardVacancyRecord]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dashboard_version = models.CharField(max_length=40)
    as_of = models.DateTimeField()
    dedup_run = models.ForeignKey(
        "vacancies.DedupRun", on_delete=models.PROTECT, related_name="dashboard_snapshots"
    )
    premium_run = models.ForeignKey(
        "premium_segments.PremiumSegmentRun",
        on_delete=models.PROTECT,
        related_name="dashboard_snapshots",
    )
    dedup_version = models.CharField(max_length=40)
    premium_classifier_version = models.CharField(max_length=80)
    green_classifier_version = models.CharField(max_length=80)
    geospatial_resolver_version = models.CharField(max_length=80)
    source_link_policy_version = models.CharField(max_length=80)
    configuration = models.JSONField(default=dict)
    input_fingerprint = models.CharField(max_length=64)
    total_vacancy_states = models.PositiveIntegerField()
    public_green_eligible_count = models.PositiveIntegerField()
    excluded_not_green_count = models.PositiveIntegerField()
    review_not_public_count = models.PositiveIntegerField()
    mappable_vacancy_count = models.PositiveIntegerField()
    unmappable_vacancy_count = models.PositiveIntegerField()
    known_publication_date_count = models.PositiveIntegerField()
    unknown_publication_date_count = models.PositiveIntegerField()
    geospatial_resolved_count = models.PositiveIntegerField()
    geospatial_review_count = models.PositiveIntegerField()
    geospatial_unresolved_count = models.PositiveIntegerField()
    private_location_protected_count = models.PositiveIntegerField()
    dedup_review_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "dashboard_snapshot"
        ordering = ["-as_of", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["dashboard_version", "as_of", "input_fingerprint"],
                name="dashboard_snapshot_exact_input_unique",
            ),
            models.CheckConstraint(
                condition=Q(input_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="dashboard_snapshot_fingerprint_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    total_vacancy_states=F("public_green_eligible_count")
                    + F("excluded_not_green_count")
                    + F("review_not_public_count")
                ),
                name="dashboard_snapshot_visibility_counts_complete",
            ),
            models.CheckConstraint(
                condition=Q(
                    public_green_eligible_count=F("mappable_vacancy_count")
                    + F("unmappable_vacancy_count")
                ),
                name="dashboard_snapshot_mapping_counts_complete",
            ),
            models.CheckConstraint(
                condition=Q(
                    known_publication_date_count=F("public_green_eligible_count")
                    - F("unknown_publication_date_count")
                ),
                name="dashboard_publication_counts_complete",
            ),
        ]


class DashboardVacancyRecord(AppendOnlyDashboardEvidence):
    class VisibilityStatus(models.TextChoices):
        PUBLIC_GREEN_CONFIRMED = "PUBLIC_GREEN_CONFIRMED", "Public green confirmed"
        EXCLUDED_NOT_GREEN = "EXCLUDED_NOT_GREEN", "Excluded not green"
        REVIEW_NOT_PUBLIC = "REVIEW_NOT_PUBLIC", "Review not public"
        MISSING_GREEN_ASSESSMENT = "MISSING_GREEN_ASSESSMENT", "Missing green assessment"

    class MappingStatus(models.TextChoices):
        MAPPABLE = "MAPPABLE", "Mappable"
        LOCATION_UNRESOLVED = "LOCATION_UNRESOLVED", "Location unresolved"
        LOCATION_REVIEW = "LOCATION_REVIEW", "Location review"
        PUBLIC_COORDINATES_MISSING = "PUBLIC_COORDINATES_MISSING", "Public coordinates missing"
        PRIVACY_RESOLUTION_MISSING = "PRIVACY_RESOLUTION_MISSING", "Privacy resolution missing"
        LOCATION_HIDDEN = "LOCATION_HIDDEN", "Location hidden"

    class SourceLinkStatus(models.TextChoices):
        CANONICAL = "CANONICAL", "Canonical"
        AGENCY_CANONICAL = "AGENCY_CANONICAL", "Agency canonical"
        ORIGINAL_ATS_LINKED = "ORIGINAL_ATS_LINKED", "Original ATS linked"
        PORTAL_KNOWN_URL_PENDING = "PORTAL_KNOWN_URL_PENDING", "Portal URL pending"
        DISCOVERY_OR_HISTORICAL = "DISCOVERY_OR_HISTORICAL", "Discovery or historical"
        EXPIRED_SOURCE = "EXPIRED_SOURCE", "Expired source"
        NO_LINK_AVAILABLE = "NO_LINK_AVAILABLE", "No link available"
        REVIEW = "REVIEW", "Review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    snapshot = models.ForeignKey(
        DashboardSnapshot, on_delete=models.PROTECT, related_name="vacancy_records"
    )
    dedup_run_vacancy_state = models.ForeignKey(
        "vacancies.DedupRunVacancyState",
        on_delete=models.PROTECT,
        related_name="dashboard_records",
    )
    run_vacancy_key = models.CharField(max_length=64)
    canonical_posting = models.ForeignKey(
        "observations.Posting", on_delete=models.PROTECT, related_name="dashboard_records"
    )
    canonical_observation = models.ForeignKey(
        "observations.PostingObservation",
        on_delete=models.PROTECT,
        related_name="dashboard_records",
    )
    green_assessment = models.ForeignKey(
        "observations.GreenRelevanceAssessment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dashboard_records",
    )
    premium_assessment = models.ForeignKey(
        "premium_segments.PremiumSegmentAssessment",
        on_delete=models.PROTECT,
        related_name="dashboard_records",
    )
    location_resolution = models.ForeignKey(
        "observations.PostingLocationResolution",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dashboard_records",
    )
    visibility_status = models.CharField(max_length=32, choices=VisibilityStatus)
    mapping_status = models.CharField(max_length=32, choices=MappingStatus)
    source_link_status = models.CharField(max_length=32, choices=SourceLinkStatus)
    selected_external_url = models.URLField(max_length=1000, blank=True)
    visible_link_label = models.CharField(max_length=40, blank=True)
    link_selection_method = models.CharField(max_length=60)
    title = models.CharField(max_length=300)
    employer = models.CharField(max_length=200, blank=True)
    safe_description = models.TextField(blank=True)
    vacancy_status = models.CharField(max_length=20)
    municipality_name = models.CharField(max_length=100, blank=True)
    canton_code = models.CharField(max_length=2, blank=True)
    source_published_date = models.DateField(null=True, blank=True)
    published_at_precision = models.CharField(max_length=30)
    published_at_parse_method = models.CharField(max_length=40)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    closed_observed_at = models.DateTimeField(null=True, blank=True)
    location_precision = models.CharField(max_length=24)
    privacy_context = models.CharField(max_length=32)
    privacy_display_level = models.CharField(max_length=24)
    location_resolution_status = models.CharField(max_length=12, blank=True)
    public_display_latitude = models.FloatField(null=True, blank=True)
    public_display_longitude = models.FloatField(null=True, blank=True)
    premium_segment = models.CharField(max_length=40)
    premium_assessment_status = models.CharField(max_length=30)
    source_name = models.CharField(max_length=100)
    source_type = models.CharField(max_length=50)
    canonical_url = models.URLField(max_length=1000, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    workload = models.CharField(max_length=100, blank=True)
    positions_count = models.PositiveIntegerField(null=True, blank=True)
    multi_hire_possible = models.BooleanField(default=False)
    episode_number = models.PositiveIntegerField()
    source_provenance = models.JSONField(default=list)
    quality_flags = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.snapshot.pk and self.dedup_run_vacancy_state.pk:
            if self.dedup_run_vacancy_state.dedup_run.pk != self.snapshot.dedup_run.pk:
                errors["dedup_run_vacancy_state"] = "state belongs to another dedup run"
            if self.run_vacancy_key != self.dedup_run_vacancy_state.run_vacancy_key:
                errors["run_vacancy_key"] = "run vacancy key does not match state"
            if self.canonical_posting.pk != self.dedup_run_vacancy_state.canonical_posting.pk:
                errors["canonical_posting"] = "canonical posting does not match state"
        if self.canonical_observation.pk and self.canonical_posting.pk:
            if self.canonical_observation.posting.pk != self.canonical_posting.pk:
                errors["canonical_observation"] = "observation belongs to another posting"
        if self.premium_assessment.pk and self.snapshot.pk:
            if self.premium_assessment.run.pk != self.snapshot.premium_run.pk:
                errors["premium_assessment"] = "assessment belongs to another premium run"
            if self.premium_assessment.posting_observation.pk != self.canonical_observation.pk:
                errors["premium_assessment"] = "assessment belongs to another observation"
            if (
                self.premium_assessment.green_relevance_assessment.pk
                if self.premium_assessment.green_relevance_assessment
                else None
            ) != (self.green_assessment.pk if self.green_assessment else None):
                errors["green_assessment"] = "green assessment does not match premium evidence"
        if self.location_resolution is not None:
            if self.location_resolution.posting_observation.pk != self.canonical_observation.pk:
                errors["location_resolution"] = "location belongs to another observation"
            if self.location_resolution.privacy_context != self.privacy_context:
                errors["location_resolution"] = "location privacy context is incompatible"
            if self.location_resolution.created_at > self.snapshot.as_of:
                errors["location_resolution"] = "future location evidence is not PIT eligible"
        if self.canonical_observation.pk:
            source = self.canonical_observation.source
            if self.source_name != source.source_name or self.source_type != source.source_type:
                errors["source_name"] = "source presentation does not match observation source"
        coordinates = (self.public_display_latitude, self.public_display_longitude)
        if any(value is not None for value in coordinates):
            if not all(value is not None and math.isfinite(value) for value in coordinates):
                errors["public_display_latitude"] = "public coordinates must be a finite pair"
            elif not (
                -90 <= self.public_display_latitude <= 90
                and -180 <= self.public_display_longitude <= 180
            ):
                errors["public_display_latitude"] = "public coordinates are outside valid ranges"
        if self.mapping_status == self.MappingStatus.MAPPABLE:
            if self.location_resolution_status != "RESOLVED":
                errors["mapping_status"] = "mappable records require a RESOLVED location"
            if self.privacy_display_level == "HIDDEN" or not all(
                value is not None for value in coordinates
            ):
                errors["mapping_status"] = "mappable records require visible coordinate pairs"
        if errors:
            raise ValidationError(errors)

    class Meta:
        db_table = "dashboard_vacancy_record"
        ordering = ["-first_seen_at", "run_vacancy_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "dedup_run_vacancy_state"],
                name="dashboard_record_snapshot_state_unique",
            ),
            models.UniqueConstraint(
                fields=["snapshot", "run_vacancy_key"],
                name="dashboard_record_snapshot_key_unique",
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
                name="dashboard_record_public_coordinate_pair",
            ),
            models.CheckConstraint(
                condition=~Q(mapping_status="MAPPABLE")
                | Q(
                    public_display_latitude__isnull=False,
                    public_display_longitude__isnull=False,
                ),
                name="dashboard_record_mappable_has_coordinates",
            ),
            models.CheckConstraint(
                condition=Q(public_display_latitude__isnull=True)
                | (Q(public_display_latitude__gte=-90) & Q(public_display_latitude__lte=90)),
                name="dashboard_public_latitude_range",
            ),
            models.CheckConstraint(
                condition=Q(public_display_longitude__isnull=True)
                | (Q(public_display_longitude__gte=-180) & Q(public_display_longitude__lte=180)),
                name="dashboard_public_longitude_range",
            ),
            models.CheckConstraint(
                condition=~Q(mapping_status="MAPPABLE")
                | (
                    Q(location_resolution_status="RESOLVED")
                    & ~Q(privacy_display_level="HIDDEN")
                    & Q(public_display_latitude__isnull=False)
                    & Q(public_display_longitude__isnull=False)
                ),
                name="dashboard_mappable_resolution_valid",
            ),
        ]
