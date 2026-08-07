from __future__ import annotations

import uuid

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class CollectionRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey("sources.Source", on_delete=models.PROTECT)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.RUNNING)
    listing_url = models.URLField(max_length=500)
    listing_raw_artifact = models.OneToOneField(
        "core.RawArtifact",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="listing_collection_run",
    )
    listings_discovered = models.PositiveIntegerField(default=0)
    details_fetched = models.PositiveIntegerField(default=0)
    observations_created = models.PositiveIntegerField(default=0)
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


class PostingObservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection_run = models.ForeignKey(
        CollectionRun, on_delete=models.PROTECT, related_name="observations"
    )
    source = models.ForeignKey("sources.Source", on_delete=models.PROTECT)
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
    location_street = models.CharField(max_length=200, blank=True)
    location_locality = models.CharField(max_length=100, blank=True)
    location_region = models.CharField(max_length=100, blank=True)
    location_postal_code = models.CharField(max_length=20, blank=True)
    location_country = models.CharField(max_length=2, blank=True)
    municipality = models.ForeignKey("reference_data.Municipality", on_delete=models.PROTECT)
    raw_artifact = models.OneToOneField(
        "core.RawArtifact", on_delete=models.PROTECT, related_name="posting_observation"
    )
    structured_payload = models.JSONField()

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

    def __str__(self) -> str:
        return f"{self.source.pk}:{self.source_posting_id}"
