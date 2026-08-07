from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from reference_data.importers import ReferenceDataError, ReferenceDataImporter


class Command(BaseCommand):
    help = "Import and validate the frozen v0.4 reference datasets idempotently."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--data-dir",
            type=Path,
            default=Path(settings.BASE_DIR) / "docs" / "research" / "v0_4",
            help="Directory containing the frozen v0.4 CSV files.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        importer = ReferenceDataImporter(options["data_dir"])
        try:
            summary = importer.run()
        except ReferenceDataError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Reference data import complete"))
        self.stdout.write(f"German-speaking municipalities: {summary.municipalities}")
        self.stdout.write(f"Public employers: {summary.public_employers}")
        self.stdout.write(f"Employment sources: {summary.employment_sources}")
        self.stdout.write(f"Salary reference sources: {summary.salary_sources}")
        self.stdout.write(f"Total source registry rows: {summary.total_sources}")
        self.stdout.write(f"Role taxonomy terms: {summary.role_terms}")
        self.stdout.write(f"Premium signals: {summary.premium_signals}")
        self.stdout.write(f"Salary references: {summary.salary_references}")
        self.stdout.write(f"City portal audits: {summary.city_audits}")
