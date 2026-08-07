from django.contrib import admin

from observations.models import CollectionRun, PostingObservation


@admin.register(CollectionRun)
class CollectionRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "status",
        "started_at",
        "finished_at",
        "listings_discovered",
        "observations_created",
    )
    list_filter = ("status", "source")
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
    readonly_fields = ("observed_at", "structured_payload")
