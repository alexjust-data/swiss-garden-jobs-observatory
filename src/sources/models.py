from __future__ import annotations

from django.db import models


class Source(models.Model):
    source_id = models.CharField(max_length=40, primary_key=True)
    source_name = models.CharField(max_length=100)
    domain = models.CharField(max_length=255)
    source_family = models.CharField(max_length=40)
    source_type = models.CharField(max_length=50)
    priority = models.CharField(max_length=10)
    coverage_scope = models.CharField(max_length=255)
    canonicality = models.CharField(max_length=50)
    platform_family = models.CharField(max_length=50, blank=True)
    access_method = models.CharField(max_length=30)
    automation_status = models.CharField(max_length=50)
    legal_review_status = models.CharField(max_length=50)
    verification_status = models.CharField(max_length=50)
    official_url = models.URLField(max_length=500)
    search_url = models.URLField(max_length=500, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "sources_source"
        ordering = ["source_id"]
        indexes = [
            models.Index(fields=["source_family", "priority"]),
            models.Index(fields=["platform_family"]),
        ]

    def __str__(self) -> str:
        return self.source_name
