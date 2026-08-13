from __future__ import annotations

import uuid
from typing import Any

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class ImmutableVacancyEvidenceError(RuntimeError):
    pass


class EvidenceQuerySet(models.QuerySet[Any]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableVacancyEvidenceError("vacancy evidence is append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableVacancyEvidenceError("vacancy evidence cannot be deleted")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableVacancyEvidenceError("vacancy evidence is append-only")


class EvidenceManager(models.Manager[Any]):
    def get_queryset(self) -> EvidenceQuerySet:
        return EvidenceQuerySet(self.model, using=self._db)

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableVacancyEvidenceError("vacancy evidence is append-only")


class AppendOnlyEvidence(models.Model):
    objects = EvidenceManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableVacancyEvidenceError("vacancy evidence is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableVacancyEvidenceError("vacancy evidence cannot be deleted")


class DedupRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dedup_version = models.CharField(max_length=40)
    normalizer_version = models.CharField(max_length=50)
    position_count_version = models.CharField(max_length=50)
    source_precedence_version = models.CharField(max_length=50)
    as_of = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status, default=Status.RUNNING)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    postings_considered = models.PositiveIntegerField(default=0)
    candidate_pairs = models.PositiveIntegerField(default=0)
    hard_key_merges = models.PositiveIntegerField(default=0)
    rule_auto_merges = models.PositiveIntegerField(default=0)
    review_pairs = models.PositiveIntegerField(default=0)
    keep_separate_pairs = models.PositiveIntegerField(default=0)
    hard_barrier_pairs = models.PositiveIntegerField(default=0)
    vacancies_created = models.PositiveIntegerField(default=0)
    episodes_created = models.PositiveIntegerField(default=0)
    input_fingerprint = models.CharField(max_length=64)
    configuration = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "dedup_run"
        ordering = ["-as_of", "-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["dedup_version", "as_of", "input_fingerprint"],
                name="dedup_run_version_asof_input_unique",
            )
        ]


class Vacancy(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CLOSED_OBSERVED = "CLOSED_OBSERVED", "Closed observed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    identity_version = models.CharField(max_length=40)
    current_status = models.CharField(max_length=20, choices=Status, default=Status.ACTIVE)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    closed_observed_at = models.DateTimeField(null=True, blank=True)
    current_episode_number = models.PositiveIntegerField(default=1)
    canonical_posting = models.ForeignKey(
        "observations.Posting",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="canonical_vacancies",
    )
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="merged_identities",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vacancy"
        indexes = [models.Index(fields=["identity_version", "current_status"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(last_seen_at__gte=F("first_seen_at")),
                name="vacancy_seen_dates_ordered",
            ),
            models.CheckConstraint(
                condition=Q(closed_observed_at__isnull=True)
                | Q(closed_observed_at__gte=F("first_seen_at")),
                name="vacancy_closed_after_first_seen",
            ),
            models.CheckConstraint(
                condition=Q(merged_into__isnull=True) | ~Q(id=F("merged_into")),
                name="vacancy_not_merged_into_self",
            ),
        ]


class VacancyPostingMembership(models.Model):
    class LinkMethod(models.TextChoices):
        INITIAL = "INITIAL", "Initial"
        HARD_KEY = "HARD_KEY", "Hard key"
        RULE_SCORE = "RULE_SCORE", "Rule score"
        HUMAN = "HUMAN", "Human"

    class EvidenceRole(models.TextChoices):
        CANONICAL = "CANONICAL", "Canonical"
        SUPPORTING = "SUPPORTING", "Supporting"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, related_name="memberships")
    posting = models.ForeignKey(
        "observations.Posting",
        on_delete=models.PROTECT,
        related_name="vacancy_memberships",
    )
    identity_version = models.CharField(max_length=40)
    link_method = models.CharField(max_length=20, choices=LinkMethod)
    dedup_decision = models.ForeignKey(
        "DedupDecision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resulting_memberships",
    )
    source_precedence_rank = models.PositiveSmallIntegerField()
    canonical_evidence_role = models.CharField(max_length=12, choices=EvidenceRole)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vacancy_posting_membership"
        constraints = [
            models.UniqueConstraint(
                fields=["posting", "identity_version"],
                name="vacancy_membership_posting_version_unique",
            )
        ]


class VacancyMembershipEvent(AppendOnlyEvidence):
    class EventType(models.TextChoices):
        LINK = "LINK", "Link"
        REASSIGN = "REASSIGN", "Reassign"
        MERGE_IDENTITY = "MERGE_IDENTITY", "Merge identity"
        HUMAN_CONFIRM = "HUMAN_CONFIRM", "Human confirm"
        CANONICAL_PROMOTE = "CANONICAL_PROMOTE", "Canonical promote"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    membership = models.ForeignKey(
        VacancyPostingMembership, on_delete=models.PROTECT, related_name="events"
    )
    from_vacancy = models.ForeignKey(
        Vacancy,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="membership_events_from",
    )
    to_vacancy = models.ForeignKey(
        Vacancy, on_delete=models.PROTECT, related_name="membership_events_to"
    )
    dedup_run = models.ForeignKey(
        DedupRun, on_delete=models.PROTECT, related_name="membership_events"
    )
    event_type = models.CharField(max_length=20, choices=EventType)
    reason = models.TextField()
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "vacancy_membership_event"


class VacancyEpisode(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CLOSED_OBSERVED = "CLOSED_OBSERVED", "Closed observed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, related_name="episodes")
    episode_number = models.PositiveIntegerField()
    opened_observed_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    closed_observed_at = models.DateTimeField(null=True, blank=True)
    reappearance_gap_days = models.PositiveIntegerField(null=True, blank=True)
    positions_count = models.PositiveIntegerField(null=True, blank=True)
    multi_hire_possible = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status, default=Status.ACTIVE)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vacancy_episode"
        ordering = ["vacancy_id", "episode_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["vacancy", "episode_number"],
                name="vacancy_episode_number_unique",
            ),
            models.CheckConstraint(
                condition=Q(positions_count__isnull=True) | Q(positions_count__gt=0),
                name="vacancy_episode_positions_positive",
            ),
            models.CheckConstraint(
                condition=Q(last_seen_at__gte=F("opened_observed_at")),
                name="vacancy_episode_seen_ordered",
            ),
            models.CheckConstraint(
                condition=Q(closed_observed_at__isnull=True)
                | Q(closed_observed_at__gte=F("opened_observed_at")),
                name="vacancy_episode_closed_ordered",
            ),
        ]


class VacancyLifecycleEvent(AppendOnlyEvidence):
    class EventType(models.TextChoices):
        NEW = "NEW", "New"
        STILL_ACTIVE = "STILL_ACTIVE", "Still active"
        CLOSED_OBSERVED = "CLOSED_OBSERVED", "Closed observed"
        REAPPEARED = "REAPPEARED", "Reappeared"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, related_name="lifecycle_events")
    episode = models.ForeignKey(
        VacancyEpisode, on_delete=models.PROTECT, related_name="lifecycle_events"
    )
    dedup_run = models.ForeignKey(
        DedupRun, on_delete=models.PROTECT, related_name="lifecycle_events"
    )
    event_type = models.CharField(max_length=20, choices=EventType)
    observed_at = models.DateTimeField()
    supporting_postings = models.JSONField(default=list)
    reason = models.TextField()
    dedup_version = models.CharField(max_length=40)
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "vacancy_lifecycle_event"


class DedupDecision(AppendOnlyEvidence):
    class Method(models.TextChoices):
        HARD_KEY = "HARD_KEY", "Hard key"
        RULE_SCORE = "RULE_SCORE", "Rule score"
        HUMAN = "HUMAN", "Human"

    class Outcome(models.TextChoices):
        AUTO_MERGE = "AUTO_MERGE", "Auto merge"
        REVIEW = "REVIEW", "Review"
        KEEP_SEPARATE = "KEEP_SEPARATE", "Keep separate"
        MERGE = "MERGE", "Merge"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dedup_run = models.ForeignKey(DedupRun, on_delete=models.PROTECT, related_name="decisions")
    posting_a = models.ForeignKey(
        "observations.Posting", on_delete=models.PROTECT, related_name="dedup_decisions_as_a"
    )
    posting_b = models.ForeignKey(
        "observations.Posting", on_delete=models.PROTECT, related_name="dedup_decisions_as_b"
    )
    observation_a = models.ForeignKey(
        "observations.PostingObservation",
        on_delete=models.PROTECT,
        related_name="dedup_decisions_as_a",
    )
    observation_b = models.ForeignKey(
        "observations.PostingObservation",
        on_delete=models.PROTECT,
        related_name="dedup_decisions_as_b",
    )
    dedup_version = models.CharField(max_length=40)
    normalizer_version = models.CharField(max_length=50)
    method = models.CharField(max_length=20, choices=Method)
    outcome = models.CharField(max_length=20, choices=Outcome)
    score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    feature_scores = models.JSONField(default=dict)
    weights = models.JSONField(default=dict)
    blocking_evidence = models.JSONField(default=dict)
    hard_barriers = models.JSONField(default=list)
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "dedup_decision"
        constraints = [
            models.CheckConstraint(
                condition=~Q(posting_a=F("posting_b")), name="dedup_decision_distinct_pair"
            ),
            models.CheckConstraint(
                condition=Q(score__isnull=True) | (Q(score__gte=0) & Q(score__lte=1)),
                name="dedup_decision_score_range",
            ),
            models.UniqueConstraint(
                fields=["dedup_run", "posting_a", "posting_b", "method"],
                name="dedup_decision_run_pair_method_unique",
            ),
        ]


class DedupReviewItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        MERGED = "MERGED", "Merged"
        KEPT_SEPARATE = "KEPT_SEPARATE", "Kept separate"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    algorithm_decision = models.OneToOneField(
        DedupDecision, on_delete=models.PROTECT, related_name="review_item"
    )
    vacancy_a = models.ForeignKey(
        Vacancy,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="review_items_as_a",
    )
    vacancy_b = models.ForeignKey(
        Vacancy,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="review_items_as_b",
    )
    run_vacancy_state_a = models.ForeignKey(
        "DedupRunVacancyState",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="review_items_as_a",
    )
    run_vacancy_state_b = models.ForeignKey(
        "DedupRunVacancyState",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="review_items_as_b",
    )
    status = models.CharField(max_length=20, choices=Status, default=Status.PENDING)
    resolution_reason = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dedup_review_item"
        constraints = [
            models.CheckConstraint(
                condition=Q(run_vacancy_state_a__isnull=True)
                | Q(run_vacancy_state_b__isnull=True)
                | ~Q(run_vacancy_state_a=F("run_vacancy_state_b")),
                name="dedup_review_run_states_distinct",
            )
        ]


class DedupReviewDecisionApplication(AppendOnlyEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target_algorithm_decision = models.OneToOneField(
        DedupDecision, on_delete=models.PROTECT, related_name="inherited_review_application"
    )
    source_human_decision = models.ForeignKey(
        DedupDecision, on_delete=models.PROTECT, related_name="review_reuse_applications"
    )
    material_fingerprint = models.CharField(max_length=64)
    fingerprint_version = models.CharField(max_length=80)
    application_method = models.CharField(max_length=50, default="MATERIAL_IDENTICAL_HUMAN_REUSE")
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "dedup_review_decision_application"

    def clean(self) -> None:
        super().clean()
        if not self.target_algorithm_decision.pk or not self.source_human_decision.pk:
            return
        from django.core.exceptions import ValidationError

        from .review_continuity import (
            FROZEN_CONFIGURATION,
            DedupContinuityValidationError,
            validate_dedup_review_application,
        )

        try:
            validate_dedup_review_application(self, FROZEN_CONFIGURATION)
        except DedupContinuityValidationError as exc:
            raise ValidationError({"evidence": str(exc)}) from exc

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableVacancyEvidenceError("vacancy evidence is append-only")
        self.full_clean()
        models.Model.save(self, *args, **kwargs)


class PositionCountEvidence(AppendOnlyEvidence):
    class Method(models.TextChoices):
        EXPLICIT_NUMERIC = "EXPLICIT_NUMERIC", "Explicit numeric"
        MULTI_HIRE_SIGNAL = "MULTI_HIRE_SIGNAL", "Multi-hire signal"
        NOT_DISCLOSED = "NOT_DISCLOSED", "Not disclosed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    posting_observation = models.ForeignKey(
        "observations.PostingObservation",
        on_delete=models.PROTECT,
        related_name="position_count_evidence",
    )
    vacancy_episode = models.ForeignKey(
        VacancyEpisode, on_delete=models.PROTECT, related_name="position_count_evidence"
    )
    extractor_version = models.CharField(max_length=50)
    positions_count = models.PositiveIntegerField(null=True, blank=True)
    multi_hire_possible = models.BooleanField(default=False)
    method = models.CharField(max_length=30, choices=Method)
    raw_evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "position_count_evidence"
        constraints = [
            models.UniqueConstraint(
                fields=["posting_observation", "vacancy_episode", "extractor_version"],
                name="position_evidence_observation_episode_version_unique",
            ),
            models.CheckConstraint(
                condition=Q(positions_count__isnull=True) | Q(positions_count__gt=0),
                name="position_evidence_count_positive",
            ),
        ]


class DedupRunVacancyState(AppendOnlyEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dedup_run = models.ForeignKey(DedupRun, on_delete=models.PROTECT, related_name="vacancy_states")
    vacancy_identity = models.ForeignKey(
        Vacancy,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="run_states",
    )
    run_vacancy_key = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Vacancy.Status)
    canonical_posting = models.ForeignKey(
        "observations.Posting",
        on_delete=models.PROTECT,
        related_name="dedup_run_canonical_states",
    )
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    closed_observed_at = models.DateTimeField(null=True, blank=True)
    episode_number = models.PositiveIntegerField(default=1)
    positions_count = models.PositiveIntegerField(null=True, blank=True)
    multi_hire_possible = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "dedup_run_vacancy_state"
        constraints = [
            models.UniqueConstraint(
                fields=["dedup_run", "run_vacancy_key"],
                name="dedup_run_vacancy_key_unique",
            ),
            models.CheckConstraint(
                condition=Q(last_seen_at__gte=F("first_seen_at")),
                name="dedup_run_vacancy_seen_ordered",
            ),
            models.CheckConstraint(
                condition=Q(closed_observed_at__isnull=True)
                | Q(closed_observed_at__gte=F("first_seen_at")),
                name="dedup_run_vacancy_closed_ordered",
            ),
            models.CheckConstraint(
                condition=Q(positions_count__isnull=True) | Q(positions_count__gt=0),
                name="dedup_run_vacancy_positions_positive",
            ),
        ]


class DedupRunPostingAssignment(AppendOnlyEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dedup_run = models.ForeignKey(
        DedupRun, on_delete=models.PROTECT, related_name="posting_assignments"
    )
    posting = models.ForeignKey(
        "observations.Posting",
        on_delete=models.PROTECT,
        related_name="dedup_run_assignments",
    )
    run_vacancy_state = models.ForeignKey(
        DedupRunVacancyState,
        on_delete=models.PROTECT,
        related_name="posting_assignments",
    )
    membership_role = models.CharField(max_length=12, choices=VacancyPostingMembership.EvidenceRole)
    link_method = models.CharField(max_length=20, choices=VacancyPostingMembership.LinkMethod)
    decision = models.ForeignKey(
        DedupDecision,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="run_assignments",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "dedup_run_posting_assignment"
        constraints = [
            models.UniqueConstraint(
                fields=["dedup_run", "posting"],
                name="dedup_run_posting_assignment_unique",
            )
        ]


class VacancyProjectionState(models.Model):
    identity_version = models.CharField(max_length=50, unique=True)
    applied_dedup_run = models.OneToOneField(
        DedupRun,
        on_delete=models.PROTECT,
        related_name="applied_projection",
    )
    applied_as_of = models.DateTimeField()
    input_fingerprint = models.CharField(max_length=64)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vacancy_projection_state"
