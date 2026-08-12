from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from observations.models import (
    CollectionRun,
    CollectionRunFetch,
    GeocoderCacheEntry,
    GeocodingReviewItem,
    GreenRelevanceAssessment,
    GreenRelevanceReviewDecision,
    Posting,
    PostingLifecycleEvent,
    PostingLocationResolution,
    PostingObservation,
)


@admin.register(CollectionRun)
class CollectionRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "status",
        "run_scope",
        "snapshot_complete",
        "source_health_status",
        "listing_total_discovered",
        "postings_in_scope",
        "started_at",
        "finished_at",
        "listings_discovered",
        "observations_created",
        "green_assessments_created",
    )
    list_filter = ("status", "run_scope", "snapshot_complete", "source_health_status", "source")
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


@admin.register(GreenRelevanceReviewDecision)
class GreenRelevanceReviewDecisionAdmin(admin.ModelAdmin):
    list_display = (
        "assessment",
        "outcome",
        "reason_code",
        "governance_version",
        "reviewed_at",
    )
    list_filter = ("outcome", "reason_code", "governance_version")
    readonly_fields = tuple(field.name for field in GreenRelevanceReviewDecision._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Posting)
class PostingAdmin(admin.ModelAdmin):
    list_display = (
        "source_posting_id",
        "source",
        "current_status",
        "first_seen_at",
        "last_seen_at",
        "negative_scan_count",
        "closed_observed_at",
    )
    list_filter = ("current_status", "source")
    search_fields = ("source_posting_id", "latest_canonical_url")
    readonly_fields = tuple(field.name for field in Posting._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(PostingLifecycleEvent)
class PostingLifecycleEventAdmin(admin.ModelAdmin):
    list_display = (
        "posting",
        "event_type",
        "observed_at",
        "source_health_status",
        "collection_run",
    )
    list_filter = ("event_type", "source_health_status")
    readonly_fields = tuple(field.name for field in PostingLifecycleEvent._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(PostingLocationResolution)
class PostingLocationResolutionAdmin(admin.ModelAdmin):
    list_display = (
        "posting_observation",
        "resolution_status",
        "municipality",
        "location_precision",
        "coordinate_source",
        "privacy_display_level",
        "resolver_version",
        "created_at",
    )
    list_filter = (
        "resolution_status",
        "location_precision",
        "coordinate_source",
        "privacy_display_level",
        "resolver_version",
    )
    readonly_fields = tuple(field.name for field in PostingLocationResolution._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(GeocoderCacheEntry)
class GeocoderCacheEntryAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "provider_version",
        "request_fingerprint",
        "http_status",
        "created_at",
    )
    readonly_fields = tuple(field.name for field in GeocoderCacheEntry._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(GeocodingReviewItem)
class GeocodingReviewItemAdmin(admin.ModelAdmin):
    list_display = (
        "posting_observation",
        "reason",
        "resolver_version",
        "review_status",
        "created_at",
    )
    list_filter = ("reason", "resolver_version", "review_status")
    readonly_fields = (
        "id",
        "posting_observation",
        "location_resolution",
        "reason",
        "candidate_evidence",
        "resolver_version",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(CollectionRunFetch)
class CollectionRunFetchAdmin(admin.ModelAdmin):
    list_display = ("collection_run", "fetch_role", "ordinal", "http_status", "final_url")
    readonly_fields = tuple(field.name for field in CollectionRunFetch._meta.fields)

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return False
