"""Core domain models placeholder for Gate-001."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ImmutableReviewAuthorityLineageImportError(RuntimeError):
    pass


class ReviewAuthorityLineageImportQuerySet(models.QuerySet["ReviewAuthorityLineageImport"]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableReviewAuthorityLineageImportError(
            "ReviewAuthorityLineageImport queryset updates are forbidden"
        )

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableReviewAuthorityLineageImportError(
            "ReviewAuthorityLineageImport queryset deletion is forbidden"
        )

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableReviewAuthorityLineageImportError(
            "ReviewAuthorityLineageImport bulk updates are forbidden"
        )


class ReviewAuthorityLineageImportManager(models.Manager["ReviewAuthorityLineageImport"]):
    def get_queryset(self) -> ReviewAuthorityLineageImportQuerySet:
        return ReviewAuthorityLineageImportQuerySet(self.model, using=self._db)

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise ImmutableReviewAuthorityLineageImportError(
            "ReviewAuthorityLineageImport bulk updates are forbidden"
        )


class RawArtifact(models.Model):
    object_key = models.CharField(max_length=255, unique=True)
    sha256_digest = models.CharField(max_length=64)
    byte_size = models.PositiveIntegerField()
    content_type = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_raw_artifact"
        indexes = [
            models.Index(fields=["sha256_digest"]),
        ]

    def __str__(self) -> str:
        return self.object_key


class ReviewAuthorityLineageImport(models.Model):
    """Append-only provenance for an exact review-authority package."""

    objects = ReviewAuthorityLineageImportManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lineage_version = models.CharField(max_length=80, unique=True)
    package_sha256 = models.CharField(max_length=64, unique=True)
    authority_registry_sha256 = models.CharField(max_length=64)
    source_snapshot_fingerprint = models.CharField(max_length=64)
    source_gate_shas = models.JSONField(default=dict)
    target_prestate_fingerprint = models.CharField(max_length=64)
    imported_authority_counts = models.JSONField(default=dict)
    reused_authority_counts = models.JSONField(default=dict)
    conflict_counts = models.JSONField(default=dict)
    replicated_at = models.DateTimeField(default=timezone.now)
    input_fingerprint = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = "review_authority_lineage_import"
        ordering = ["replicated_at", "pk"]

    @staticmethod
    def _valid_sha256(value: str) -> bool:
        return len(value) == 64 and all(character in "0123456789abcdef" for character in value)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.lineage_version != "review-authority-lineage-v0.1":
            errors["lineage_version"] = "unsupported review-authority lineage version"
        for field in (
            "package_sha256",
            "authority_registry_sha256",
            "source_snapshot_fingerprint",
            "target_prestate_fingerprint",
            "input_fingerprint",
        ):
            if not self._valid_sha256(str(getattr(self, field))):
                errors[field] = "must be a lower-case SHA-256 digest"
        expected_gates = {
            "gate_011e": "cbf1054b329843ea3fff7eeac77ea9342df60147",
            "gate_011g": "3f8e5cacc191309188e142ebf28ae0d1115e95e7",
            "c1_baseline": "520b68d989d36abfc382143458b30d1f3bad96b2",
        }
        if self.source_gate_shas != expected_gates:
            errors["source_gate_shas"] = "must equal the frozen C1 governance SHAs"
        for field in (
            "imported_authority_counts",
            "reused_authority_counts",
            "conflict_counts",
        ):
            value: Any = getattr(self, field)
            if not isinstance(value, dict) or any(
                not isinstance(item, int) or item < 0 for item in value.values()
            ):
                errors[field] = "must contain non-negative integer counts"
        if self.conflict_counts != {"total": 0}:
            errors["conflict_counts"] = "a committed lineage batch must have zero conflicts"
        from core.review_authority_lineage import lineage_batch_input_fingerprint

        expected_input = lineage_batch_input_fingerprint(
            lineage_version=self.lineage_version,
            package_sha256=self.package_sha256,
            authority_registry_sha256=self.authority_registry_sha256,
            source_snapshot_fingerprint=self.source_snapshot_fingerprint,
            target_prestate_fingerprint=self.target_prestate_fingerprint,
            source_gate_shas=self.source_gate_shas,
            imported_authority_counts=self.imported_authority_counts,
            reused_authority_counts=self.reused_authority_counts,
            conflict_counts=self.conflict_counts,
        )
        if self.input_fingerprint != expected_input:
            errors["input_fingerprint"] = "does not match the governed immutable batch payload"
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableReviewAuthorityLineageImportError(
                "ReviewAuthorityLineageImport is append-only"
            )
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableReviewAuthorityLineageImportError(
            "ReviewAuthorityLineageImport cannot be deleted"
        )
