from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class ImmutablePremiumEvidenceError(RuntimeError):
    pass


SHA256_VALIDATOR = RegexValidator(
    regex=r"^[0-9a-f]{64}$",
    message="value must be a lowercase 64-character SHA-256 digest",
)


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
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutablePremiumEvidenceError("premium evidence cannot be deleted")


class EmployerProfileEvidence(AppendOnlyPremiumEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(
        "sources.Source", on_delete=models.PROTECT, related_name="premium_employer_evidence"
    )
    employer_identity_key = models.CharField(max_length=200)
    employer_name = models.CharField(max_length=300)
    evidence_text = models.TextField()
    evidence_type = models.CharField(max_length=50)
    source_url = models.URLField(max_length=1000, blank=True)
    available_at = models.DateTimeField()
    raw_sha256 = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    evidence_version = models.CharField(max_length=50)
    provenance = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "premium_employer_profile_evidence"
        indexes = [models.Index(fields=["source", "employer_identity_key", "available_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(raw_sha256__regex=r"^[0-9a-f]{64}$"),
                name="premium_profile_raw_sha256_valid",
            ),
            models.CheckConstraint(
                condition=~Q(employer_identity_key=""),
                name="premium_profile_identity_key_nonempty",
            ),
            models.UniqueConstraint(
                fields=[
                    "source",
                    "employer_identity_key",
                    "available_at",
                    "raw_sha256",
                    "evidence_version",
                ],
                name="premium_profile_material_evidence_unique",
            ),
        ]


class PremiumSegmentRun(AppendOnlyPremiumEvidence):
    class Status(models.TextChoices):
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    as_of = models.DateTimeField()
    classifier_version = models.CharField(max_length=80)
    normalizer_version = models.CharField(max_length=80)
    taxonomy_version = models.CharField(max_length=80)
    taxonomy_sha256 = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    configuration = models.JSONField(default=dict)
    input_fingerprint = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
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
            ),
            models.CheckConstraint(
                condition=Q(taxonomy_sha256__regex=r"^[0-9a-f]{64}$"),
                name="premium_run_taxonomy_sha256_valid",
            ),
            models.CheckConstraint(
                condition=Q(input_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="premium_run_input_fingerprint_valid",
            ),
            models.CheckConstraint(
                condition=Q(finished_at__gte=F("started_at")),
                name="premium_run_timestamps_ordered",
            ),
            models.CheckConstraint(
                condition=Q(
                    observations_considered=F("classified_count")
                    + F("review_count")
                    + F("no_sufficient_evidence_count")
                    + F("skipped_not_green_count")
                ),
                name="premium_run_status_counts_complete",
            ),
            models.CheckConstraint(
                condition=Q(
                    observations_considered=F("private_residential_standard_count")
                    + F("private_residential_premium_count")
                    + F("private_estate_direct_count")
                    + F("unknown_count")
                ),
                name="premium_run_segment_counts_complete",
            ),
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
    green_review_decision = models.ForeignKey(
        "observations.GreenRelevanceReviewDecision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="premium_segment_assessments",
    )
    effective_green_result = models.CharField(
        max_length=20,
        choices=[
            ("GREEN_CONFIRMED", "Green confirmed"),
            ("REVIEW", "Review"),
            ("NOT_GREEN", "Not green"),
            ("MISSING", "Missing"),
        ],
        default="MISSING",
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
    matched_signal_ids = models.JSONField(default=list, blank=True)
    matched_fields_and_scopes = models.JSONField(default=list, blank=True)
    matched_evidence = models.JSONField(default=list, blank=True)
    prohibited_inferences = models.JSONField(default=list, blank=True)
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
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        assessment_status="CLASSIFIED",
                        segment__in=[
                            "PRIVATE_RESIDENTIAL_STANDARD",
                            "PRIVATE_RESIDENTIAL_PREMIUM",
                            "PRIVATE_ESTATE_DIRECT",
                        ],
                    )
                    | Q(
                        assessment_status__in=[
                            "REVIEW",
                            "NO_SUFFICIENT_EVIDENCE",
                            "SKIPPED_NOT_GREEN",
                        ],
                        segment="UNKNOWN",
                    )
                ),
                name="premium_assessment_status_segment_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(segment="UNKNOWN")
                    | Q(privacy_context="PRIVATE_RESIDENCE")
                    | Q(privacy_context="CONFIDENTIAL_PRIVATE_RESIDENCE")
                ),
                name="premium_assessment_private_segment_protected",
            ),
        ]
        indexes = [
            models.Index(fields=["assessment_status", "segment"]),
            models.Index(fields=["posting_observation", "created_at"]),
        ]

    def clean(self) -> None:
        super().clean()
        if (
            self.green_relevance_assessment is not None
            and self.green_review_decision is None
            and self.effective_green_result == "MISSING"
        ):
            self.effective_green_result = self.green_relevance_assessment.result
        if (
            self.green_relevance_assessment is not None
            and self.green_relevance_assessment.posting_observation.pk
            != self.posting_observation.pk
        ):
            raise ValidationError(
                {"green_relevance_assessment": "green assessment belongs to another observation"}
            )
        if (
            self.green_review_decision is not None
            and self.green_review_decision.assessment.pk != self.green_relevance_assessment.pk
        ):
            raise ValidationError(
                {"green_review_decision": "decision belongs to another assessment"}
            )
        if self.green_relevance_assessment is None and self.effective_green_result != "MISSING":
            raise ValidationError({"effective_green_result": "missing assessment requires MISSING"})


class PremiumSegmentAssessmentEmployerEvidence(AppendOnlyPremiumEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(
        PremiumSegmentAssessment,
        on_delete=models.PROTECT,
        related_name="employer_evidence_links",
    )
    employer_profile_evidence = models.ForeignKey(
        EmployerProfileEvidence,
        on_delete=models.PROTECT,
        related_name="assessment_links",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "premium_segment_assessment_employer_evidence"
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "employer_profile_evidence"],
                name="premium_assessment_employer_evidence_unique",
            )
        ]


class PremiumSegmentReviewItem(AppendOnlyPremiumEvidence):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.OneToOneField(
        PremiumSegmentAssessment, on_delete=models.PROTECT, related_name="review_item"
    )
    reason = models.CharField(max_length=200)
    conflicting_or_insufficient_evidence = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=12, choices=Status, default=Status.PENDING)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "premium_segment_review_item"
        constraints = [
            models.CheckConstraint(
                condition=Q(status="PENDING"), name="premium_review_initial_status_pending"
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.assessment.assessment_status != "REVIEW":
            raise ValidationError({"assessment": "review item requires a REVIEW assessment"})
