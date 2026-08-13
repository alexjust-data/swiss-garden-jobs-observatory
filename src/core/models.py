"""Core domain models placeholder for Gate-001."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ImmutableReviewAuthorityLineageImportError(RuntimeError):
    pass


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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lineage_version = models.CharField(max_length=80)
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
        constraints = [
            models.UniqueConstraint(
                fields=["lineage_version", "package_sha256"],
                name="review_authority_lineage_package_unique",
            )
        ]

    @staticmethod
    def _valid_sha256(value: str) -> bool:
        return len(value) == 64 and all(character in "0123456789abcdef" for character in value)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        for field in (
            "package_sha256",
            "authority_registry_sha256",
            "source_snapshot_fingerprint",
            "target_prestate_fingerprint",
            "input_fingerprint",
        ):
            if not self._valid_sha256(str(getattr(self, field))):
                errors[field] = "must be a lower-case SHA-256 digest"
        expected_gates = {"gate_011e", "gate_011g", "c1_baseline"}
        if set(self.source_gate_shas) != expected_gates:
            errors["source_gate_shas"] = "must pin GATE-011E, GATE-011G and the C1 baseline"
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
