from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from core.review_authority_lineage import (
    GOVERNANCE_DOCUMENT_PATH,
    ReviewAuthorityLineageError,
    import_package,
    load_json,
    verify_registry_against_merged_governance,
)


class Command(BaseCommand):
    help = "Preflight or atomically import an exact GATE-011G-C1 authority package"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--package", required=True)
        parser.add_argument("--registry", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        package = load_json(Path(str(options["package"])))
        registry = load_json(Path(str(options["registry"])))
        try:
            verify_registry_against_merged_governance(
                registry, GOVERNANCE_DOCUMENT_PATH
            )
            with transaction.atomic():
                result = import_package(package, registry)
                if bool(options["dry_run"]):
                    transaction.set_rollback(True)
        except ReviewAuthorityLineageError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            " ".join(
                (
                    f"batch={result.batch.pk}",
                    f"dry_run={bool(options['dry_run'])}",
                    f"green_imported={result.imported_green}",
                    f"green_reused={result.reused_green}",
                    f"dedup_imported={result.imported_dedup}",
                    f"dedup_reused={result.reused_dedup}",
                    f"green_apps_imported={result.imported_green_applications}",
                    f"dedup_apps_imported={result.imported_dedup_applications}",
                )
            )
        )
