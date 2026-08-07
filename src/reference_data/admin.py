from django.contrib import admin

from reference_data.models import (
    CityPortalAudit,
    Municipality,
    PremiumSignal,
    PublicEmployer,
    RoleSearchTerm,
    SalaryReference,
)


@admin.register(Municipality)
class MunicipalityAdmin(admin.ModelAdmin):
    list_display = (
        "bfs_code",
        "municipality_name",
        "canton_code",
        "statistical_city",
        "degurb2021",
    )
    list_filter = ("canton_code", "statistical_city", "degurb2021")
    search_fields = ("municipality_name", "bfs_code")


@admin.register(PublicEmployer)
class PublicEmployerAdmin(admin.ModelAdmin):
    list_display = (
        "universe_id",
        "employer_name",
        "employer_level",
        "canton_code",
        "priority_tier",
    )
    list_filter = ("employer_level", "canton_code", "priority_tier", "verification_status")
    search_fields = ("universe_id", "employer_name")


@admin.register(CityPortalAudit)
class CityPortalAuditAdmin(admin.ModelAdmin):
    list_display = ("queue_id", "municipality_name", "canton_code", "portal_audit_status")
    list_filter = ("canton_code", "portal_audit_status", "platform_family")
    search_fields = ("queue_id", "municipality_name")


@admin.register(RoleSearchTerm)
class RoleSearchTermAdmin(admin.ModelAdmin):
    list_display = ("term_id", "search_term_de", "canonical_role_family", "term_type")
    list_filter = ("canonical_role_family", "term_type", "include_default")
    search_fields = ("term_id", "search_term_de")


@admin.register(PremiumSignal)
class PremiumSignalAdmin(admin.ModelAdmin):
    list_display = ("signal_id", "search_term", "signal_group", "base_weight", "default_segment")
    list_filter = ("signal_group", "evidence_scope", "default_segment")
    search_fields = ("signal_id", "search_term")


@admin.register(SalaryReference)
class SalaryReferenceAdmin(admin.ModelAdmin):
    list_display = ("reference_id", "reference_type", "reference_scope", "valid_from", "valid_to")
    list_filter = ("reference_type", "currency", "gross_net", "source_tier")
    search_fields = ("reference_id", "reference_scope", "qualification_level")
