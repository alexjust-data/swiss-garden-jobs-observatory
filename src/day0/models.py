# mypy: disable-error-code="attr-defined"
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class ImmutableDay0EvidenceError(RuntimeError):
    pass


class Day0EvidenceQuerySet(models.QuerySet[Any]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableDay0EvidenceError("Day-0 evidence updates are forbidden")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableDay0EvidenceError("Day-0 evidence deletion is forbidden")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableDay0EvidenceError("Day-0 evidence bulk updates are forbidden")


class Day0EvidenceManager(models.Manager[Any]):
    def get_queryset(self) -> Day0EvidenceQuerySet:
        return Day0EvidenceQuerySet(self.model, using=self._db)

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableDay0EvidenceError("Day-0 evidence bulk updates are forbidden")


class AppendOnlyDay0Evidence(models.Model):
    objects = Day0EvidenceManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableDay0EvidenceError(f"{type(self).__name__} is append-only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableDay0EvidenceError(f"{type(self).__name__} cannot be deleted")


class Day0SourceUniverse(AppendOnlyDay0Evidence):
    class ThresholdPolicyStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    universe_version = models.CharField(max_length=80)
    policy_version = models.CharField(max_length=80)
    threshold_policy_status = models.CharField(max_length=12, choices=ThresholdPolicyStatus)
    required_completion_threshold = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    source_registry_sha256 = models.CharField(max_length=64)
    coverage_matrix_sha256 = models.CharField(max_length=64)
    configuration = models.JSONField(default=dict)
    input_fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "day0_source_universe"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["universe_version", "input_fingerprint"],
                name="day0_universe_version_input_unique",
            ),
            models.CheckConstraint(
                condition=Q(source_registry_sha256__regex=r"^[0-9a-f]{64}$"),
                name="day0_universe_registry_hash_valid",
            ),
            models.CheckConstraint(
                condition=Q(coverage_matrix_sha256__regex=r"^[0-9a-f]{64}$"),
                name="day0_universe_coverage_hash_valid",
            ),
            models.CheckConstraint(
                condition=Q(input_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="day0_universe_fingerprint_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        threshold_policy_status="PENDING",
                        required_completion_threshold__isnull=True,
                    )
                    | Q(
                        threshold_policy_status="ACCEPTED",
                        required_completion_threshold__gt=0,
                        required_completion_threshold__lte=1,
                    )
                ),
                name="day0_universe_threshold_policy_coherent",
            ),
        ]


class Day0AuthorizationPolicy(AppendOnlyDay0Evidence):
    class PolicyStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy_version = models.CharField(max_length=80, db_index=True)
    threshold_policy_status = models.CharField(max_length=12, choices=PolicyStatus)
    required_completion_threshold = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    freshness_policy_status = models.CharField(max_length=12, choices=PolicyStatus)
    required_source_max_age_hours = models.PositiveIntegerField(null=True, blank=True)
    configuration = models.JSONField(default=dict)
    input_fingerprint = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "day0_authorization_policy"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(input_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="day0_policy_fingerprint_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        threshold_policy_status="PENDING",
                        required_completion_threshold__isnull=True,
                    )
                    | Q(
                        threshold_policy_status="ACCEPTED",
                        required_completion_threshold__gt=0,
                        required_completion_threshold__lte=1,
                    )
                ),
                name="day0_policy_threshold_coherent",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        freshness_policy_status="PENDING",
                        required_source_max_age_hours__isnull=True,
                    )
                    | Q(
                        freshness_policy_status="ACCEPTED",
                        required_source_max_age_hours__gt=0,
                    )
                ),
                name="day0_policy_freshness_coherent",
            ),
        ]


class Day0AuthorizationPolicyDesignation(AppendOnlyDay0Evidence):
    class AuthorityBasis(models.TextChoices):
        MERGED_GOVERNANCE_DECISION = (
            "MERGED_GOVERNANCE_DECISION",
            "Merged governance decision",
        )

    REQUIRED_GOVERNANCE_FIELDS = frozenset(
        {
            "pr_number",
            "merged_sha",
            "final_policy_commit",
            "final_tree_commit",
            "adr_path",
        }
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    designation_version = models.CharField(max_length=80)
    policy_version = models.CharField(max_length=80)
    authoritative_policy = models.ForeignKey(
        Day0AuthorizationPolicy,
        on_delete=models.PROTECT,
        related_name="authority_designations",
    )
    authority_basis = models.CharField(max_length=40, choices=AuthorityBasis)
    governance_evidence = models.JSONField(default=dict)
    effective_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)
    input_fingerprint = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = "day0_authorization_policy_designation"
        ordering = ["-effective_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["designation_version", "policy_version"],
                name="day0_policy_designation_version_unique",
            ),
            models.CheckConstraint(
                condition=Q(input_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="day0_policy_designation_fingerprint_valid",
            ),
        ]

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "designation_version": self.designation_version,
            "policy_version": self.policy_version,
            "authoritative_policy_fingerprint": self.authoritative_policy.input_fingerprint,
            "authority_basis": self.authority_basis,
            "governance_evidence": self.governance_evidence,
            "effective_at": self.effective_at.isoformat(),
        }

    def expected_input_fingerprint(self) -> str:
        canonical = json.dumps(
            self.fingerprint_payload(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if (
            self.authoritative_policy_id
            and self.policy_version != self.authoritative_policy.policy_version
        ):
            errors["policy_version"] = "Designation and artifact policy versions differ."
        missing = self.REQUIRED_GOVERNANCE_FIELDS - set(self.governance_evidence)
        if missing:
            errors["governance_evidence"] = "Missing governance evidence: " + ", ".join(
                sorted(missing)
            )
        if self.effective_at and self.created_at and self.effective_at > self.created_at:
            errors["effective_at"] = "Authority cannot become effective after its evidence exists."
        if self.authoritative_policy_id and self.effective_at:
            expected = self.expected_input_fingerprint()
            if self.input_fingerprint != expected:
                errors["input_fingerprint"] = "Designation fingerprint does not match its evidence."
        conflict = Day0AuthorizationPolicyDesignation.objects.filter(
            designation_version=self.designation_version,
            policy_version=self.policy_version,
        )
        if self.pk:
            conflict = conflict.exclude(pk=self.pk)
        if self.designation_version and self.policy_version and conflict.exists():
            errors["policy_version"] = "Conflicting authority designation already exists."
        if errors:
            raise ValidationError(errors)


class Day0SourceUniverseEntry(AppendOnlyDay0Evidence):
    class Classification(models.TextChoices):
        REQUIRED = "DAY0_REQUIRED", "Day-0 required"
        SUPPORTING = "DAY0_SUPPORTING", "Day-0 supporting"
        DEFERRED = "DEFERRED", "Deferred"
        NOT_APPLICABLE = "NOT_APPLICABLE", "Not applicable"
        BLOCKED = "BLOCKED_PENDING_ACCESS_REVIEW", "Blocked pending access review"

    class TargetRole(models.TextChoices):
        REQUIRED = "REQUIRED", "Required"
        SUPPORTING = "SUPPORTING", "Supporting"
        NONE = "NONE", "None"

    class AccessStatus(models.TextChoices):
        READY = "READY_FOR_IMPLEMENTATION", "Ready for implementation"
        BLOCKED = "BLOCKED_PENDING_ACCESS_REVIEW", "Blocked pending access review"
        NOT_APPLICABLE = "NOT_APPLICABLE", "Not applicable"
        UNKNOWN_LEGACY = "UNKNOWN_LEGACY", "Unknown legacy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    universe = models.ForeignKey(
        Day0SourceUniverse, on_delete=models.PROTECT, related_name="entries"
    )
    source = models.ForeignKey("sources.Source", on_delete=models.PROTECT)
    classification = models.CharField(max_length=40, choices=Classification)
    target_role = models.CharField(max_length=12, choices=TargetRole)
    access_status = models.CharField(
        max_length=40, choices=AccessStatus, default=AccessStatus.UNKNOWN_LEGACY
    )
    reason = models.TextField()
    access_reason = models.TextField(default="Legacy source-universe entry")
    canton_code = models.CharField(max_length=2, blank=True)
    source_name = models.CharField(max_length=200)
    source_family = models.CharField(max_length=80)
    source_type = models.CharField(max_length=80)
    priority = models.CharField(max_length=12)
    coverage_scope = models.CharField(max_length=200)
    canonicality = models.CharField(max_length=80)
    platform_family = models.CharField(max_length=100)
    automation_status = models.CharField(max_length=100)
    legal_review_status = models.CharField(max_length=100)
    verification_status = models.CharField(max_length=100)
    existing_adapter_reuse = models.BooleanField(default=False)
    new_adapter_required = models.BooleanField(default=False)
    blocking_issue = models.TextField(blank=True)
    implementation_batch = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "day0_source_universe_entry"
        ordering = ["implementation_batch", "source_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["universe", "source"], name="day0_universe_source_unique"
            ),
            models.CheckConstraint(
                condition=(
                    Q(target_role="NONE", implementation_batch__isnull=True)
                    | Q(
                        target_role__in=["REQUIRED", "SUPPORTING"],
                        implementation_batch__isnull=False,
                    )
                ),
                name="day0_entry_batch_matches_target",
            ),
        ]


class Day0ReadinessAssessment(AppendOnlyDay0Evidence):
    class Status(models.TextChoices):
        AUTHORIZED = "DAY_0_AUTHORIZED", "Day-0 authorized"
        NOT_READY = "DAY_0_NOT_READY", "Day-0 not ready"
        POLICY_PENDING = "DAY_0_THRESHOLD_POLICY_PENDING", "Day-0 threshold policy pending"
        BLOCKED_ACCESS = "DAY_0_BLOCKED_BY_SOURCE_ACCESS", "Day-0 blocked by source access"
        BLOCKED_QUALITY = "DAY_0_BLOCKED_BY_DATA_QUALITY", "Day-0 blocked by data quality"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    readiness_version = models.CharField(max_length=80)
    as_of = models.DateTimeField()
    source_universe = models.ForeignKey(
        Day0SourceUniverse, on_delete=models.PROTECT, related_name="assessments"
    )
    authorization_policy = models.ForeignKey(
        Day0AuthorizationPolicy,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assessments",
    )
    policy_version = models.CharField(max_length=80)
    dedup_run = models.ForeignKey("vacancies.DedupRun", on_delete=models.PROTECT)
    premium_run = models.ForeignKey("premium_segments.PremiumSegmentRun", on_delete=models.PROTECT)
    dashboard_snapshot = models.ForeignKey("dashboard.DashboardSnapshot", on_delete=models.PROTECT)
    readiness_status = models.CharField(max_length=40, choices=Status)
    selected_source_ids = models.JSONField(default=list)
    selected_collection_run_ids = models.JSONField(default=list, blank=True)
    metrics = models.JSONField(default=dict)
    critical_review_ids = models.JSONField(default=list, blank=True)
    noncritical_review_ids = models.JSONField(default=list, blank=True)
    blockers = models.JSONField(default=list, blank=True)
    required_source_count = models.PositiveIntegerField()
    supporting_source_count = models.PositiveIntegerField()
    deferred_source_count = models.PositiveIntegerField()
    not_applicable_source_count = models.PositiveIntegerField(default=0)
    blocked_source_count = models.PositiveIntegerField()
    blocked_required_source_count = models.PositiveIntegerField(default=0)
    blocked_supporting_source_count = models.PositiveIntegerField(default=0)
    blocked_other_source_count = models.PositiveIntegerField(default=0)
    implemented_required_source_count = models.PositiveIntegerField()
    required_complete_count = models.PositiveIntegerField(default=0)
    required_healthy_count = models.PositiveIntegerField(default=0)
    required_freshness_valid_count = models.PositiveIntegerField(default=0)
    required_full_source_healthy_count = models.PositiveIntegerField()
    required_source_completion_ratio = models.DecimalField(
        max_digits=7, decimal_places=6, null=True, blank=True
    )
    healthy_source_ratio = models.DecimalField(
        max_digits=7, decimal_places=6, null=True, blank=True
    )
    critical_review_count = models.PositiveIntegerField()
    noncritical_review_count = models.PositiveIntegerField()
    critical_green_review_count = models.PositiveIntegerField(default=0)
    critical_dedup_review_count = models.PositiveIntegerField(default=0)
    other_critical_review_count = models.PositiveIntegerField(default=0)
    green_confirmed_count = models.PositiveIntegerField(default=0)
    green_review_count = models.PositiveIntegerField(default=0)
    not_green_count = models.PositiveIntegerField(default=0)
    missing_green_count = models.PositiveIntegerField(default=0)
    observed_postings = models.PositiveIntegerField()
    selected_source_postings = models.PositiveIntegerField(default=0)
    active_unique_vacancies = models.PositiveIntegerField()
    known_positions_total = models.PositiveIntegerField()
    vacancies_unknown_position_count = models.PositiveIntegerField()
    multi_hire_possible_count = models.PositiveIntegerField()
    input_fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "day0_readiness_assessment"
        ordering = ["-as_of", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source_universe",
                    "authorization_policy",
                    "as_of",
                    "dedup_run",
                    "premium_run",
                    "dashboard_snapshot",
                    "input_fingerprint",
                ],
                name="day0_readiness_v2_exact_input_unique",
            ),
            models.CheckConstraint(
                condition=Q(input_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="day0_readiness_fingerprint_valid",
            ),
            models.CheckConstraint(
                condition=Q(implemented_required_source_count__lte=F("required_source_count")),
                name="day0_implemented_required_within_total",
            ),
            models.CheckConstraint(
                condition=Q(required_full_source_healthy_count__lte=F("required_source_count")),
                name="day0_healthy_required_within_total",
            ),
            models.CheckConstraint(
                condition=Q(required_source_completion_ratio__isnull=True)
                | (
                    Q(required_source_completion_ratio__gte=0)
                    & Q(required_source_completion_ratio__lte=1)
                ),
                name="day0_required_ratio_valid",
            ),
            models.CheckConstraint(
                condition=Q(healthy_source_ratio__isnull=True)
                | (Q(healthy_source_ratio__gte=0) & Q(healthy_source_ratio__lte=1)),
                name="day0_health_ratio_valid",
            ),
        ]

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.dashboard_snapshot_id:
            snapshot = self.dashboard_snapshot
            if snapshot.dedup_run_id != self.dedup_run_id:
                errors["dedup_run"] = "Dashboard snapshot belongs to another DedupRun."
            if snapshot.premium_run_id != self.premium_run_id:
                errors["premium_run"] = "Dashboard snapshot belongs to another PremiumSegmentRun."
            if snapshot.as_of != self.as_of:
                errors["as_of"] = "Dashboard snapshot as_of differs from readiness as_of."
        if (
            self.authorization_policy_id
            and self.policy_version != self.authorization_policy.policy_version
        ):
            errors["policy_version"] = "Policy version does not match authorization policy."
        if errors:
            raise ValidationError(errors)


class Day0ReadinessSourceEvidence(AppendOnlyDay0Evidence):
    class CompletionStatus(models.TextChoices):
        COMPLETE_HEALTHY = "COMPLETE_HEALTHY", "Complete and healthy"
        COMPLETE_FRESHNESS_PENDING = "COMPLETE_FRESHNESS_PENDING", "Complete; freshness pending"
        NO_ELIGIBLE_RUN = "NO_ELIGIBLE_RUN", "No eligible run"
        DEGRADED = "DEGRADED", "Degraded"
        OUTAGE = "OUTAGE", "Outage"
        INCOMPLETE = "INCOMPLETE", "Incomplete"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(
        Day0ReadinessAssessment, on_delete=models.PROTECT, related_name="source_evidence"
    )
    universe_entry = models.ForeignKey(Day0SourceUniverseEntry, on_delete=models.PROTECT)
    source = models.ForeignKey("sources.Source", on_delete=models.PROTECT)
    collection_run = models.ForeignKey(
        "observations.CollectionRun",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="day0_legacy_selected_evidence",
    )
    latest_activity_run = models.ForeignKey(
        "observations.CollectionRun",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="day0_latest_activity_evidence",
    )
    latest_full_source_run = models.ForeignKey(
        "observations.CollectionRun",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="day0_latest_full_source_evidence",
    )
    latest_health_run = models.ForeignKey(
        "observations.CollectionRun",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="day0_latest_health_evidence",
    )
    completion_status = models.CharField(max_length=32, choices=CompletionStatus)
    is_complete = models.BooleanField(default=False)
    is_healthy = models.BooleanField(default=False)
    structurally_complete = models.BooleanField(default=False)
    currently_healthy = models.BooleanField(default=False)
    freshness_valid = models.BooleanField(null=True, blank=True)
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "day0_readiness_source_evidence"
        ordering = ["source_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "universe_entry"],
                name="day0_readiness_source_entry_unique",
            ),
            models.CheckConstraint(
                condition=~Q(completion_status="COMPLETE_HEALTHY")
                | Q(
                    is_complete=True,
                    is_healthy=True,
                    structurally_complete=True,
                    currently_healthy=True,
                    freshness_valid=True,
                    latest_full_source_run__isnull=False,
                    latest_health_run__isnull=False,
                )
                | Q(
                    is_complete=True,
                    is_healthy=True,
                    collection_run__isnull=False,
                    latest_full_source_run__isnull=True,
                    latest_health_run__isnull=True,
                    freshness_valid__isnull=True,
                ),
                name="day0_complete_healthy_v2_coherent",
            ),
        ]

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.universe_entry_id and self.assessment_id:
            if self.universe_entry.universe_id != self.assessment.source_universe_id:
                errors["universe_entry"] = "Universe entry belongs to another source universe."
        if self.universe_entry_id and self.source_id != self.universe_entry.source_id:
            errors["source"] = "Source differs from universe entry source."
        for field in (
            "collection_run",
            "latest_activity_run",
            "latest_full_source_run",
            "latest_health_run",
        ):
            run = getattr(self, field)
            if run is None:
                continue
            if run.source_id != self.source_id:
                errors[field] = "CollectionRun belongs to another source."
            if self.assessment_id and run.finished_at and run.finished_at > self.assessment.as_of:
                errors[field] = "CollectionRun is after assessment as_of."
        if errors:
            raise ValidationError(errors)
