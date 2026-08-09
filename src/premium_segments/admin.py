from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import (
    EmployerProfileEvidence,
    PremiumSegmentAssessment,
    PremiumSegmentReviewItem,
    PremiumSegmentRun,
)


class ReadOnlyPremiumAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> list[str]:
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


for model in (
    EmployerProfileEvidence,
    PremiumSegmentRun,
    PremiumSegmentAssessment,
    PremiumSegmentReviewItem,
):
    admin.site.register(model, ReadOnlyPremiumAdmin)
