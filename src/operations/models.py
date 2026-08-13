from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ImmutableOperationalEvidenceError(RuntimeError):
    pass


class AppendOnlyOperationalQuerySet(models.QuerySet[Any]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableOperationalEvidenceError("operational evidence is append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableOperationalEvidenceError("operational evidence cannot be deleted")


class AppendOnlyOperationalManager(models.Manager[Any]):
    def get_queryset(self) -> AppendOnlyOperationalQuerySet:
        return AppendOnlyOperationalQuerySet(self.model, using=self._db)


class AppendOnlyOperationalEvidence(models.Model):
    objects = AppendOnlyOperationalManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableOperationalEvidenceError("operational evidence is append-only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableOperationalEvidenceError("operational evidence cannot be deleted")


class ObservatoryCycle(models.Model):
    source_attempts: models.Manager[ObservatorySourceAttempt]
    operational_events: models.Manager[OperationalEvent]

    class Trigger(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        SCHEDULED = "SCHEDULED", "Scheduled"
        RECOVERY = "RECOVERY", "Recovery"

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        SUCCEEDED_NOT_AUTHORIZED = "SUCCEEDED_NOT_AUTHORIZED", "Succeeded, not authorized"
        FAILED_COLLECTION = "FAILED_COLLECTION", "Collection failed"
        FAILED_COMPLETENESS = "FAILED_COMPLETENESS", "Completeness failed"
        FAILED_CONTINUITY = "FAILED_CONTINUITY", "Continuity failed"
        FAILED_DEDUP = "FAILED_DEDUP", "Dedup failed"
        FAILED_PREMIUM = "FAILED_PREMIUM", "Premium failed"
        FAILED_DASHBOARD = "FAILED_DASHBOARD", "Dashboard failed"
        FAILED_READINESS = "FAILED_READINESS", "Readiness failed"
        ABORTED_CONCURRENCY = "ABORTED_CONCURRENCY", "Concurrency refused"

    class Health(models.TextChoices):
        GREEN = "GREEN", "Green"
        AMBER = "AMBER", "Amber"
        RED = "RED", "Red"
        UNKNOWN = "UNKNOWN", "Unknown"

    TERMINAL = frozenset(
        {
            Status.SUCCEEDED,
            Status.SUCCEEDED_NOT_AUTHORIZED,
            Status.FAILED_COLLECTION,
            Status.FAILED_COMPLETENESS,
            Status.FAILED_CONTINUITY,
            Status.FAILED_DEDUP,
            Status.FAILED_PREMIUM,
            Status.FAILED_DASHBOARD,
            Status.FAILED_READINESS,
            Status.ABORTED_CONCURRENCY,
        }
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle_version = models.CharField(max_length=80)
    trigger = models.CharField(max_length=12, choices=Trigger)
    requested_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=40, choices=Status, default=Status.PLANNED)
    target_cohort_version = models.CharField(max_length=80)
    selected_source_ids = models.JSONField(default=list)
    configuration = models.JSONField(default=dict)
    configuration_fingerprint = models.CharField(max_length=64)
    stage_statuses = models.JSONField(default=dict, blank=True)
    final_cutoff = models.DateTimeField(null=True, blank=True)
    dedup_run = models.ForeignKey(
        "vacancies.DedupRun", null=True, blank=True, on_delete=models.PROTECT
    )
    premium_run = models.ForeignKey(
        "premium_segments.PremiumSegmentRun", null=True, blank=True, on_delete=models.PROTECT
    )
    dashboard_snapshot = models.ForeignKey(
        "dashboard.DashboardSnapshot", null=True, blank=True, on_delete=models.PROTECT
    )
    readiness_assessment = models.ForeignKey(
        "day0.Day0ReadinessAssessment", null=True, blank=True, on_delete=models.PROTECT
    )
    operational_health = models.CharField(max_length=12, choices=Health, default=Health.UNKNOWN)
    quality_state = models.JSONField(default=dict, blank=True)
    continuity_counts = models.JSONField(default=dict, blank=True)
    failure_code = models.CharField(max_length=80, blank=True)
    failure_evidence = models.JSONField(default=dict, blank=True)
    code_git_sha = models.CharField(max_length=64, default="UNKNOWN")

    class Meta:
        db_table = "observatory_cycle"
        ordering = ["-requested_at", "-id"]
        indexes = [
            models.Index(fields=["status", "-requested_at"]),
            models.Index(fields=["cycle_version", "-finished_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(configuration_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="observatory_cycle_configuration_fp_valid",
            ),
            models.CheckConstraint(
                condition=Q(final_cutoff__isnull=True) | Q(finished_at__isnull=False),
                name="observatory_cycle_cutoff_requires_finish",
            ),
        ]

    def clean(self) -> None:
        if self.status in self.TERMINAL and self.finished_at is None:
            raise ValidationError({"finished_at": "terminal cycles require finished_at"})
        if self.status == self.Status.RUNNING and self.started_at is None:
            raise ValidationError({"started_at": "running cycles require started_at"})
        if self.final_cutoff and any(
            item is None
            for item in (
                getattr(self, "dedup_run_id", None),
                getattr(self, "premium_run_id", None),
                getattr(self, "dashboard_snapshot_id", None),
                getattr(self, "readiness_assessment_id", None),
            )
        ):
            raise ValidationError("a final cutoff requires the complete aligned PIT chain")
        if self.final_cutoff and all(
            item is not None
            for item in (
                getattr(self, "dedup_run_id", None),
                getattr(self, "premium_run_id", None),
                getattr(self, "dashboard_snapshot_id", None),
                getattr(self, "readiness_assessment_id", None),
            )
        ):
            artifacts = (
                self.dedup_run,
                self.premium_run,
                self.dashboard_snapshot,
                self.readiness_assessment,
            )
            if any(artifact.as_of != self.final_cutoff for artifact in artifacts):
                raise ValidationError("all final PIT artifacts must use the cycle cutoff")
            if self.dashboard_snapshot.dedup_run_id != self.dedup_run.pk:
                raise ValidationError("Dashboard references another DedupRun")
            if self.dashboard_snapshot.premium_run_id != self.premium_run.pk:
                raise ValidationError("Dashboard references another PremiumSegmentRun")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            previous = ObservatoryCycle.objects.get(pk=self.pk)
            if previous.status in {self.Status.SUCCEEDED, self.Status.SUCCEEDED_NOT_AUTHORIZED}:
                raise ImmutableOperationalEvidenceError("completed cycles are immutable")
            if previous.configuration_fingerprint != self.configuration_fingerprint:
                raise ImmutableOperationalEvidenceError("cycle configuration is immutable")
            if previous.selected_source_ids != self.selected_source_ids:
                raise ImmutableOperationalEvidenceError("cycle cohort is immutable")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableOperationalEvidenceError("cycles cannot be deleted")


class ObservatorySourceAttempt(AppendOnlyOperationalEvidence):
    class Result(models.TextChoices):
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        REUSED = "REUSED", "Reused in same-cycle retry"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle = models.ForeignKey(
        ObservatoryCycle, on_delete=models.PROTECT, related_name="source_attempts"
    )
    source = models.ForeignKey("sources.Source", on_delete=models.PROTECT)
    attempt_number = models.PositiveSmallIntegerField(default=1)
    result = models.CharField(max_length=12, choices=Result)
    collection_run = models.ForeignKey(
        "observations.CollectionRun", null=True, blank=True, on_delete=models.PROTECT
    )
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    runtime_ms = models.PositiveBigIntegerField(default=0)
    run_status = models.CharField(max_length=20, blank=True)
    source_health = models.CharField(max_length=20, blank=True)
    snapshot_complete = models.BooleanField(default=False)
    counter_consistent = models.BooleanField(default=False)
    metrics = models.JSONField(default=dict, blank=True)
    failure_code = models.CharField(max_length=80, blank=True)
    failure_detail = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "observatory_source_attempt"
        ordering = ["cycle_id", "source_id", "attempt_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["cycle", "source", "attempt_number"],
                name="observatory_source_attempt_unique",
            ),
            models.CheckConstraint(
                condition=(Q(result="FAILED") | Q(collection_run__isnull=False)),
                name="observatory_success_attempt_has_run",
            ),
        ]

    def clean(self) -> None:
        collection_run_id = getattr(self, "collection_run_id", None)
        source_id = getattr(self, "source_id", None)
        if collection_run_id and self.collection_run.source_id != source_id:
            raise ValidationError({"collection_run": "CollectionRun belongs to another Source"})
        if self.finished_at < self.started_at:
            raise ValidationError({"finished_at": "attempt finish precedes start"})


class OperationalEvent(AppendOnlyOperationalEvidence):
    class Severity(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"
        CRITICAL = "CRITICAL", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle = models.ForeignKey(
        ObservatoryCycle, on_delete=models.PROTECT, related_name="operational_events"
    )
    occurred_at = models.DateTimeField(default=timezone.now)
    severity = models.CharField(max_length=12, choices=Severity)
    code = models.CharField(max_length=80)
    source = models.ForeignKey("sources.Source", null=True, blank=True, on_delete=models.PROTECT)
    artifact_type = models.CharField(max_length=80, blank=True)
    artifact_id = models.CharField(max_length=100, blank=True)
    detail = models.JSONField(default=dict)
    deduplication_fingerprint = models.CharField(max_length=64)

    class Meta:
        db_table = "operational_event"
        ordering = ["occurred_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cycle", "deduplication_fingerprint"],
                name="operational_event_cycle_fingerprint_unique",
            ),
            models.CheckConstraint(
                condition=Q(deduplication_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="operational_event_fp_valid",
            ),
        ]
