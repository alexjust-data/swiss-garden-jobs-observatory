"""Core domain models placeholder for Gate-001."""

from __future__ import annotations

from django.db import models


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
