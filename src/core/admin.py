"""Admin registration for Gate-001 models."""

from __future__ import annotations

from django.contrib import admin

from .models import RawArtifact

admin.site.register(RawArtifact)
