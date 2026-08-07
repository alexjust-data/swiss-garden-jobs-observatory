from __future__ import annotations

from django.db import models


class Municipality(models.Model):
    bfs_code = models.PositiveIntegerField(primary_key=True)
    snapshot_date = models.DateField()
    municipality_name = models.CharField(max_length=100)
    canton_code = models.CharField(max_length=2)
    canton_name = models.CharField(max_length=100)
    district = models.CharField(max_length=100, blank=True)
    bfs_language_region_code = models.PositiveSmallIntegerField()
    language_region = models.CharField(max_length=30)
    statistical_city = models.BooleanField()
    degurb2021 = models.PositiveSmallIntegerField()
    priority_tier = models.CharField(max_length=40)

    class Meta:
        db_table = "reference_municipality"
        ordering = ["bfs_code"]
        indexes = [
            models.Index(fields=["canton_code"]),
            models.Index(fields=["statistical_city"]),
            models.Index(fields=["degurb2021"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(degurb2021__in=[1, 2, 3]),
                name="reference_municipality_degurb_valid",
            )
        ]

    def __str__(self) -> str:
        return f"{self.municipality_name} ({self.bfs_code})"


class PublicEmployer(models.Model):
    universe_id = models.CharField(max_length=30, primary_key=True)
    employer_level = models.CharField(max_length=20)
    country_code = models.CharField(max_length=2)
    canton_code = models.CharField(max_length=2, blank=True)
    canton_name = models.CharField(max_length=100, blank=True)
    employer_name = models.CharField(max_length=150)
    municipality = models.OneToOneField(
        Municipality,
        db_column="bfs_code",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="public_employer",
    )
    language_region = models.CharField(max_length=30)
    priority_tier = models.CharField(max_length=40)
    expected_green_service_units = models.TextField(blank=True)
    canonical_portal_status = models.CharField(max_length=30)
    canonical_portal_url = models.URLField(max_length=500, blank=True)
    portal_platform = models.CharField(max_length=50, blank=True)
    verification_status = models.CharField(max_length=50)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "reference_public_employer"
        ordering = ["universe_id"]
        indexes = [
            models.Index(fields=["employer_level"]),
            models.Index(fields=["canton_code"]),
            models.Index(fields=["priority_tier"]),
        ]

    def __str__(self) -> str:
        return self.employer_name


class CityPortalAudit(models.Model):
    queue_id = models.CharField(max_length=20, primary_key=True)
    municipality = models.OneToOneField(
        Municipality,
        db_column="bfs_code",
        on_delete=models.PROTECT,
        related_name="city_portal_audit",
    )
    priority = models.CharField(max_length=10)
    canton_code = models.CharField(max_length=2)
    municipality_name = models.CharField(max_length=100)
    district = models.CharField(max_length=100, blank=True)
    degurb2021 = models.PositiveSmallIntegerField()
    canonical_portal_url = models.URLField(max_length=500, blank=True)
    platform_family = models.CharField(max_length=50)
    portal_audit_status = models.CharField(max_length=30)
    green_unit_hint = models.CharField(max_length=255, blank=True)
    search_query_1 = models.TextField()
    search_query_2 = models.TextField()
    acceptance_test = models.TextField()

    class Meta:
        db_table = "reference_city_portal_audit"
        ordering = ["queue_id"]
        indexes = [
            models.Index(fields=["portal_audit_status"]),
            models.Index(fields=["platform_family"]),
        ]

    def __str__(self) -> str:
        return self.municipality_name


class RoleSearchTerm(models.Model):
    term_id = models.CharField(max_length=10, primary_key=True)
    canonical_role_family = models.CharField(max_length=40)
    canonical_specialization = models.CharField(max_length=40)
    search_term_de = models.CharField(max_length=100)
    term_type = models.CharField(max_length=30)
    include_default = models.CharField(max_length=20)
    public_relevance = models.CharField(max_length=20)
    default_access_level_hint = models.CharField(max_length=20)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "reference_role_search_term"
        ordering = ["term_id"]
        indexes = [
            models.Index(fields=["canonical_role_family"]),
            models.Index(fields=["term_type", "include_default"]),
        ]

    def __str__(self) -> str:
        return self.search_term_de


class PremiumSignal(models.Model):
    signal_id = models.CharField(max_length=10, primary_key=True)
    signal_group = models.CharField(max_length=40)
    search_term = models.CharField(max_length=100)
    evidence_scope = models.CharField(max_length=30)
    base_weight = models.DecimalField(max_digits=5, decimal_places=4)
    default_segment = models.CharField(max_length=40)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "reference_premium_signal"
        ordering = ["signal_id"]
        indexes = [
            models.Index(fields=["signal_group"]),
            models.Index(fields=["default_segment"]),
        ]

    def __str__(self) -> str:
        return self.search_term


class SalaryReference(models.Model):
    reference_id = models.CharField(max_length=60, primary_key=True)
    reference_type = models.CharField(max_length=40)
    reference_scope = models.CharField(max_length=150)
    qualification_level = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=3)
    gross_net = models.CharField(max_length=10)
    amount_monthly_raw = models.CharField(max_length=50, blank=True)
    amount_monthly_min = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    amount_monthly_max = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    payments_per_year = models.PositiveSmallIntegerField(null=True, blank=True)
    amount_annual_raw = models.CharField(max_length=50, blank=True)
    amount_annual_min = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    amount_annual_max = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    amount_hourly_base_raw = models.CharField(max_length=50, blank=True)
    amount_hourly_base_min = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    amount_hourly_base_max = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    applicability = models.CharField(max_length=80)
    source_tier = models.CharField(max_length=50)
    source_url = models.URLField(max_length=500)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "reference_salary"
        ordering = ["reference_id"]
        indexes = [
            models.Index(fields=["reference_type"]),
            models.Index(fields=["valid_from", "valid_to"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_monthly_min__gte=0)
                | models.Q(amount_monthly_min__isnull=True),
                name="reference_salary_monthly_min_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_monthly_max__gte=models.F("amount_monthly_min"))
                | models.Q(amount_monthly_max__isnull=True),
                name="reference_salary_monthly_range_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_annual_min__gte=0)
                | models.Q(amount_annual_min__isnull=True),
                name="reference_salary_annual_min_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_annual_max__gte=models.F("amount_annual_min"))
                | models.Q(amount_annual_max__isnull=True),
                name="reference_salary_annual_range_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_hourly_base_min__gte=0)
                | models.Q(amount_hourly_base_min__isnull=True),
                name="reference_salary_hourly_min_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_hourly_base_max__gte=models.F("amount_hourly_base_min"))
                | models.Q(amount_hourly_base_max__isnull=True),
                name="reference_salary_hourly_range_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.reference_id
