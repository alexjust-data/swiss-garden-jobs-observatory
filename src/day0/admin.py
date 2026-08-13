from django.contrib import admin

from .models import (
    Day0AuthorizationPolicy,
    Day0AuthorizationPolicyDesignation,
    Day0ReadinessAssessment,
    Day0ReadinessSourceEvidence,
    Day0SourceUniverse,
    Day0SourceUniverseEntry,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Day0AuthorizationPolicy, ReadOnlyAdmin)
admin.site.register(Day0AuthorizationPolicyDesignation, ReadOnlyAdmin)
admin.site.register(Day0SourceUniverse, ReadOnlyAdmin)
admin.site.register(Day0SourceUniverseEntry, ReadOnlyAdmin)
admin.site.register(Day0ReadinessAssessment, ReadOnlyAdmin)
admin.site.register(Day0ReadinessSourceEvidence, ReadOnlyAdmin)
