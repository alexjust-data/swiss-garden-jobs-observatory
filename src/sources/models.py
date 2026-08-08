from __future__ import annotations

import uuid

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


class SourceEndpoint(models.Model):
    class EndpointRole(models.TextChoices):
        LANDING = "LANDING", "Landing"
        LISTING = "LISTING", "Listing"
        DETAIL = "DETAIL", "Detail"
        API = "API", "API"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="endpoints")
    endpoint_role = models.CharField(max_length=12, choices=EndpointRole)
    platform_family = models.CharField(max_length=50)
    scheme = models.CharField(max_length=10, default="https")
    host = models.CharField(max_length=255)
    base_url = models.URLField(max_length=1000)
    enabled = models.BooleanField(default=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "source_endpoint"
        ordering = ["source_id", "endpoint_role", "base_url"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "endpoint_role", "base_url"],
                name="source_endpoint_role_url_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source.pk}:{self.endpoint_role}:{self.host}"
