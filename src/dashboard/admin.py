from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import DashboardSnapshot, DashboardVacancyRecord


class ReadOnlyDashboardAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> list[str]:
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(DashboardSnapshot)
class DashboardSnapshotAdmin(ReadOnlyDashboardAdmin):
    list_display = ("id", "as_of", "dashboard_version", "public_green_eligible_count")


@admin.register(DashboardVacancyRecord)
class DashboardVacancyRecordAdmin(ReadOnlyDashboardAdmin):
    list_display = ("run_vacancy_key", "title", "visibility_status", "mapping_status")
