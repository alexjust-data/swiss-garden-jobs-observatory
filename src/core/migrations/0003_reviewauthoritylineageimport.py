# Generated for GATE-011G-C1.

import uuid

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_rename_core_raw_artifact_sha256_idx_core_raw_ar_sha256__84b00a_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReviewAuthorityLineageImport",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("lineage_version", models.CharField(max_length=80)),
                ("package_sha256", models.CharField(max_length=64, unique=True)),
                ("authority_registry_sha256", models.CharField(max_length=64)),
                ("source_snapshot_fingerprint", models.CharField(max_length=64)),
                ("source_gate_shas", models.JSONField(default=dict)),
                ("target_prestate_fingerprint", models.CharField(max_length=64)),
                ("imported_authority_counts", models.JSONField(default=dict)),
                ("reused_authority_counts", models.JSONField(default=dict)),
                ("conflict_counts", models.JSONField(default=dict)),
                ("replicated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("input_fingerprint", models.CharField(max_length=64, unique=True)),
            ],
            options={
                "db_table": "review_authority_lineage_import",
                "ordering": ["replicated_at", "pk"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("lineage_version", "package_sha256"),
                        name="review_authority_lineage_package_unique",
                    )
                ],
            },
        )
    ]
