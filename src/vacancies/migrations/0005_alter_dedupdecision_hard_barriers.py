# Generated for GATE-011G-C1.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vacancies", "0004_dedupreviewdecisionapplication"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dedupdecision",
            name="hard_barriers",
            field=models.JSONField(blank=True, default=list),
        )
    ]
