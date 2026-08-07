from django.contrib import admin

from sources.models import Source


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("source_id", "source_name", "source_family", "priority", "automation_status")
    list_filter = ("source_family", "priority", "automation_status", "legal_review_status")
    search_fields = ("source_id", "source_name", "domain")
