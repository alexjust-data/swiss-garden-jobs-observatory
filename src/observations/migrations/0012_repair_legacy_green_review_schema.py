from django.db import migrations

TABLE = "green_relevance_review_decision"


def repair_legacy_schema(apps, schema_editor) -> None:
    connection = schema_editor.connection
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, TABLE)
        }
        if "decision" in columns and "outcome" not in columns:
            cursor.execute(
                f"ALTER TABLE {quote(TABLE)} RENAME COLUMN "
                f"{quote('decision')} TO {quote('outcome')}"
            )
        if "rationale" in columns and "reason" not in columns:
            cursor.execute(
                f"ALTER TABLE {quote(TABLE)} RENAME COLUMN "
                f"{quote('rationale')} TO {quote('reason')}"
            )
        cursor.execute(
            f"ALTER TABLE {quote(TABLE)} ALTER COLUMN {quote('outcome')} TYPE varchar(30)"
        )

        constraints = connection.introspection.get_constraints(cursor, TABLE)
        for name, details in constraints.items():
            if details.get("unique") and details.get("columns") == ["assessment_id"]:
                cursor.execute(
                    f"ALTER TABLE {quote(TABLE)} DROP CONSTRAINT {quote(name)}"
                )
        constraints = connection.introspection.get_constraints(cursor, TABLE)
        unique_name = "green_review_decision_assessment_version_unique"
        if unique_name not in constraints:
            cursor.execute(
                f"ALTER TABLE {quote(TABLE)} ADD CONSTRAINT {quote(unique_name)} "
                f"UNIQUE ({quote('assessment_id')}, {quote('governance_version')})"
            )
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS {quote('green_relev_assessm_5f6516_idx')} "
            f"ON {quote(TABLE)} "
            f"({quote('assessment_id')}, {quote('reviewed_at')}, {quote('created_at')})"
        )
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS {quote('green_relev_governa_b51f6c_idx')} "
            f"ON {quote(TABLE)} ({quote('governance_version')}, {quote('outcome')})"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("observations", "0011_greenrelevancereviewdecisionapplication"),
    ]

    operations = [
        migrations.RunPython(repair_legacy_schema, reverse_code=migrations.RunPython.noop),
    ]
