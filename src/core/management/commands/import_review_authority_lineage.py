from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from core.review_authority_lineage import (
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
        parser.add_argument(
            "--designation",
            default="docs/day0/gate_011g_c1_review_authority_package_designation_v0_1.json",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--governance-document",
            default="docs/day0/gate_011e_critical_review_resolution_v0_1.md",
        )

    def handle(self, *args: object, **options: object) -> None:
        package = load_json(Path(str(options["package"])))
        registry = load_json(Path(str(options["registry"])))
        designation = load_json(Path(str(options["designation"])))
        try:
            verify_registry_against_merged_governance(
                registry, Path(str(options["governance_document"]))
            )
            with transaction.atomic():
                result = import_package(package, registry, designation)
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
