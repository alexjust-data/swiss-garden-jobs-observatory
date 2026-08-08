import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "observations",
            "0008_remove_postinglocationresolution_location_resolution_observation_version_unique_and_more",
        )
    ]
    operations = [
        migrations.AlterField(
            model_name="postingobservation",
            name="municipality",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="reference_data.municipality",
            ),
        ),
        migrations.CreateModel(
            name="CollectionRunFetch",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("fetch_role", models.CharField(max_length=20)),
                ("ordinal", models.PositiveIntegerField()),
                ("requested_url", models.URLField(max_length=1000)),
                ("final_url", models.URLField(max_length=1000)),
                ("http_status", models.PositiveSmallIntegerField()),
                ("content_type", models.CharField(max_length=255)),
                ("evidence", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "collection_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="fetches",
                        to="observations.collectionrun",
                    ),
                ),
                (
                    "raw_artifact",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="collection_run_fetches",
                        to="core.rawartifact",
                    ),
                ),
            ],
            options={
                "db_table": "collection_run_fetch",
                "ordering": ["collection_run_id", "fetch_role", "ordinal"],
            },
        ),
        migrations.AddConstraint(
            model_name="collectionrunfetch",
            constraint=models.UniqueConstraint(
                fields=("collection_run", "fetch_role", "ordinal"),
                name="collection_run_fetch_role_ordinal_unique",
            ),
        ),
    ]
