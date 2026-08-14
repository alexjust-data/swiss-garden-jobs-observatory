from django.contrib import admin

from .models import ObservatoryCycle, ObservatorySourceAttempt, OperationalEvent


class ReadOnlyOperationalAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: object | None = None) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: object | None = None) -> bool:
        return False


@admin.register(ObservatoryCycle)
class ObservatoryCycleAdmin(ReadOnlyOperationalAdmin):
    list_display = ("id", "status", "trigger", "operational_health", "final_cutoff")
    readonly_fields = [field.name for field in ObservatoryCycle._meta.fields]


admin.site.register(ObservatorySourceAttempt, ReadOnlyOperationalAdmin)
admin.site.register(OperationalEvent, ReadOnlyOperationalAdmin)
