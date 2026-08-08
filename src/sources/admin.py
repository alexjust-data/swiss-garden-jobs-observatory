from django.contrib import admin

from sources.models import Source, SourceEndpoint


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("source_id", "source_name", "source_family", "priority", "automation_status")
    list_filter = ("source_family", "priority", "automation_status", "legal_review_status")
    search_fields = ("source_id", "source_name", "domain")


@admin.register(SourceEndpoint)
class SourceEndpointAdmin(admin.ModelAdmin):
    list_display = ("source", "endpoint_role", "platform_family", "host", "enabled")
    list_filter = ("endpoint_role", "platform_family", "enabled")
    search_fields = ("source__source_id", "host", "base_url")
