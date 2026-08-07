"""Initial migration for gate-001 baseline."""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RawArtifact",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("object_key", models.CharField(max_length=255, unique=True)),
                ("sha256_digest", models.CharField(max_length=64)),
                ("byte_size", models.PositiveIntegerField()),
                ("content_type", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "core_raw_artifact",
                "indexes": [
                    models.Index(fields=["sha256_digest"], name="core_raw_artifact_sha256_idx"),
                ],
            },
        )
    ]
