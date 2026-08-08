import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sources", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="SourceEndpoint",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "endpoint_role",
                    models.CharField(
                        choices=[
                            ("LANDING", "Landing"),
                            ("LISTING", "Listing"),
                            ("DETAIL", "Detail"),
                            ("API", "API"),
                        ],
                        max_length=12,
                    ),
                ),
                ("platform_family", models.CharField(max_length=50)),
                ("scheme", models.CharField(default="https", max_length=10)),
                ("host", models.CharField(max_length=255)),
                ("base_url", models.URLField(max_length=1000)),
                ("enabled", models.BooleanField(default=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("evidence", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="endpoints",
                        to="sources.source",
                    ),
                ),
            ],
            options={
                "db_table": "source_endpoint",
                "ordering": ["source_id", "endpoint_role", "base_url"],
            },
        ),
        migrations.AddConstraint(
            model_name="sourceendpoint",
            constraint=models.UniqueConstraint(
                fields=("source", "endpoint_role", "base_url"),
                name="source_endpoint_role_url_unique",
            ),
        ),
    ]
