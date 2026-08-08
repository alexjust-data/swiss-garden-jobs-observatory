from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from observations.models import CollectionRun, GreenRelevanceAssessment, PostingObservation


@admin.register(CollectionRun)
class CollectionRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "status",
        "run_scope",
        "snapshot_complete",
        "started_at",
        "finished_at",
        "listings_discovered",
        "observations_created",
        "green_assessments_created",
    )
    list_filter = ("status", "run_scope", "snapshot_complete", "source")
    readonly_fields = ("started_at", "finished_at")


@admin.register(PostingObservation)
class PostingObservationAdmin(admin.ModelAdmin):
    list_display = (
        "source_posting_id",
        "title",
        "source",
        "municipality",
        "date_posted",
        "valid_through",
        "observed_at",
    )
    list_filter = ("source", "municipality", "date_posted")
    search_fields = ("source_posting_id", "title", "canonical_url")
    readonly_fields = tuple(field.name for field in PostingObservation._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(GreenRelevanceAssessment)
class GreenRelevanceAssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "posting_observation",
        "result",
        "classifier_version",
        "taxonomy_version",
        "created_at",
    )
    list_filter = ("result", "classifier_version", "taxonomy_version")
    readonly_fields = tuple(field.name for field in GreenRelevanceAssessment._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
