"""Admin registration for Gate-001 models."""

from __future__ import annotations

from django.contrib import admin

from .models import RawArtifact, ReviewAuthorityLineageImport

admin.site.register(RawArtifact)
admin.site.register(ReviewAuthorityLineageImport)
