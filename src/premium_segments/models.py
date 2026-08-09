from __future__ import annotations

import uuid
from typing import Any

from django.db import models
from django.db.models import Q
from django.utils import timezone


class ImmutablePremiumEvidenceError(RuntimeError):
    pass


class PremiumEvidenceQuerySet(models.QuerySet[Any]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutablePremiumEvidenceError("premium evidence is append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutablePremiumEvidenceError("premium evidence cannot be deleted")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutablePremiumEvidenceError("premium evidence bulk updates are forbidden")


class PremiumEvidenceManager(models.Manager[Any]):
    def get_queryset(self) -> PremiumEvidenceQuerySet:
        return PremiumEvidenceQuerySet(self.model, using=self._db)

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutablePremiumEvidenceError("premium evidence bulk updates are forbidden")


class AppendOnlyPremiumEvidence(models.Model):
    objects = PremiumEvidenceManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutablePremiumEvidenceError("premium evidence is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutablePremiumEvidenceError("premium evidence cannot be deleted")


class EmployerProfileEvidence(AppendOnlyPremiumEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer_name = models.CharField(max_length=300)
    evidence_text = models.TextField()
    evidence_type = models.CharField(max_length=50)
    source_url = models.URLField(max_length=1000, blank=True)
    available_at = models.DateTimeField()
    raw_sha256 = models.CharField(max_length=64)
    evidence_version = models.CharField(max_length=50)
    provenance = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "premium_employer_profile_evidence"
        indexes = [models.Index(fields=["employer_name", "available_at"])]


class PremiumSegmentRun(AppendOnlyPremiumEvidence):
    class Status(models.TextChoices):
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    as_of = models.DateTimeField()
    classifier_version = models.CharField(max_length=80)
    normalizer_version = models.CharField(max_length=80)
    taxonomy_version = models.CharField(max_length=80)
    taxonomy_sha256 = models.CharField(max_length=64)
    configuration = models.JSONField(default=dict)
    input_fingerprint = models.CharField(max_length=64)
    observations_considered = models.PositiveIntegerField(default=0)
    green_confirmed_eligible = models.PositiveIntegerField(default=0)
    classified_count = models.PositiveIntegerField(default=0)
    review_count = models.PositiveIntegerField(default=0)
    no_sufficient_evidence_count = models.PositiveIntegerField(default=0)
    skipped_not_green_count = models.PositiveIntegerField(default=0)
    private_residential_standard_count = models.PositiveIntegerField(default=0)
    private_residential_premium_count = models.PositiveIntegerField(default=0)
    private_estate_direct_count = models.PositiveIntegerField(default=0)
    unknown_count = models.PositiveIntegerField(default=0)
    prohibited_inference_only_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField()

    class Meta:
        db_table = "premium_segment_run"
        ordering = ["-as_of", "-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "as_of",
                    "classifier_version",
                    "normalizer_version",
                    "taxonomy_sha256",
                    "input_fingerprint",
                ],
                name="premium_run_exact_input_unique",
            )
        ]


class PremiumSegmentAssessment(AppendOnlyPremiumEvidence):
    class Segment(models.TextChoices):
        PRIVATE_RESIDENTIAL_STANDARD = (
            "PRIVATE_RESIDENTIAL_STANDARD",
            "Private residential standard",
        )
        PRIVATE_RESIDENTIAL_PREMIUM = "PRIVATE_RESIDENTIAL_PREMIUM", "Private residential premium"
        PRIVATE_ESTATE_DIRECT = "PRIVATE_ESTATE_DIRECT", "Private estate direct"
        UNKNOWN = "UNKNOWN", "Unknown"

    class Status(models.TextChoices):
        CLASSIFIED = "CLASSIFIED", "Classified"
        REVIEW = "REVIEW", "Review"
        NO_SUFFICIENT_EVIDENCE = "NO_SUFFICIENT_EVIDENCE", "No sufficient evidence"
        SKIPPED_NOT_GREEN = "SKIPPED_NOT_GREEN", "Skipped not green"

    class EvidenceStrength(models.TextChoices):
        STRONG = "STRONG", "Strong"
        MODERATE = "MODERATE", "Moderate"
        WEAK = "WEAK", "Weak"
        NONE = "NONE", "None"

    class PrivacyContext(models.TextChoices):
        PUBLIC_OR_NON_RESIDENTIAL = "PUBLIC_OR_NON_RESIDENTIAL", "Public or non-residential"
        PRIVATE_RESIDENCE = "PRIVATE_RESIDENCE", "Private residence"
        CONFIDENTIAL_PRIVATE_RESIDENCE = (
            "CONFIDENTIAL_PRIVATE_RESIDENCE",
            "Confidential private residence",
        )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(PremiumSegmentRun, on_delete=models.PROTECT, related_name="assessments")
    posting_observation = models.ForeignKey(
        "observations.PostingObservation",
        on_delete=models.PROTECT,
        related_name="premium_segment_assessments",
    )
    green_relevance_assessment = models.ForeignKey(
        "observations.GreenRelevanceAssessment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="premium_segment_assessments",
    )
    employer_profile_evidence = models.ForeignKey(
        EmployerProfileEvidence,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="premium_segment_assessments",
    )
    segment = models.CharField(max_length=40, choices=Segment)
    assessment_status = models.CharField(max_length=30, choices=Status)
    method = models.CharField(max_length=50)
    evidence_strength = models.CharField(max_length=12, choices=EvidenceStrength)
    matched_signal_ids = models.JSONField(default=list)
    matched_fields_and_scopes = models.JSONField(default=list)
    matched_evidence = models.JSONField(default=list)
    prohibited_inferences = models.JSONField(default=list)
    privacy_context = models.CharField(
        max_length=32, choices=PrivacyContext, default=PrivacyContext.PUBLIC_OR_NON_RESIDENTIAL
    )
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "premium_segment_assessment"
        ordering = ["run_id", "posting_observation_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "posting_observation"],
                name="premium_assessment_run_observation_unique",
            )
        ]
        indexes = [
            models.Index(fields=["assessment_status", "segment"]),
            models.Index(fields=["posting_observation", "created_at"]),
        ]


class PremiumSegmentReviewItem(AppendOnlyPremiumEvidence):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.OneToOneField(
        PremiumSegmentAssessment, on_delete=models.PROTECT, related_name="review_item"
    )
    reason = models.CharField(max_length=200)
    conflicting_or_insufficient_evidence = models.JSONField(default=list)
    status = models.CharField(max_length=12, choices=Status, default=Status.PENDING)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "premium_segment_review_item"
        constraints = [
            models.CheckConstraint(
                condition=Q(status="PENDING"), name="premium_review_initial_status_pending"
            )
        ]
