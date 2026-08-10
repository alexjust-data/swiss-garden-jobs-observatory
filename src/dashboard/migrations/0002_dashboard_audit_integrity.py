from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="dashboardvacancyrecord",
            name="location_resolution_status",
            field=models.CharField(blank=True, max_length=12),
        ),
        migrations.AddConstraint(
            model_name="dashboardsnapshot",
            constraint=models.CheckConstraint(
                condition=Q(
                    known_publication_date_count=F("public_green_eligible_count")
                    - F("unknown_publication_date_count")
                ),
                name="dashboard_publication_counts_complete",
            ),
        ),
        migrations.AddConstraint(
            model_name="dashboardvacancyrecord",
            constraint=models.CheckConstraint(
                condition=Q(public_display_latitude__isnull=True)
                | (Q(public_display_latitude__gte=-90) & Q(public_display_latitude__lte=90)),
                name="dashboard_public_latitude_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="dashboardvacancyrecord",
            constraint=models.CheckConstraint(
                condition=Q(public_display_longitude__isnull=True)
                | (Q(public_display_longitude__gte=-180) & Q(public_display_longitude__lte=180)),
                name="dashboard_public_longitude_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="dashboardvacancyrecord",
            constraint=models.CheckConstraint(
                condition=~Q(mapping_status="MAPPABLE")
                | (
                    Q(location_resolution_status="RESOLVED")
                    & ~Q(privacy_display_level="HIDDEN")
                    & Q(public_display_latitude__isnull=False)
                    & Q(public_display_longitude__isnull=False)
                ),
                name="dashboard_mappable_resolution_valid",
            ),
        ),
    ]
