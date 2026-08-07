from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from collectors.winterthur import WINTERTHUR_SOURCE_ID, WinterthurCollector
from sources.models import Source


class Command(BaseCommand):
    help = "Run one manual point-in-time collection against jobs.winterthur.ch."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--posting-id", action="append", dest="posting_ids")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--delay-seconds", type=float, default=1.0)
        parser.add_argument(
            "--acknowledge-automation-review",
            action="store_true",
            help="Acknowledge the source registry legal review status for this manual run.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        source = Source.objects.get(source_id=WINTERTHUR_SOURCE_ID)
        if (
            source.legal_review_status != "APPROVED"
            and not options["acknowledge_automation_review"]
        ):
            raise CommandError(
                f"{source.source_id} legal_review_status is "
                f"{source.legal_review_status!r}; pass --acknowledge-automation-review "
                "only after an explicit manual review."
            )

        posting_ids = set(options["posting_ids"] or []) or None
        run = WinterthurCollector(delay_seconds=options["delay_seconds"]).collect(
            posting_ids=posting_ids,
            limit=options["limit"],
        )
        self.stdout.write(self.style.SUCCESS("Winterthur collection complete"))
        self.stdout.write(f"Run: {run.id}")
        self.stdout.write(f"Listings discovered: {run.listings_discovered}")
        self.stdout.write(f"Details fetched: {run.details_fetched}")
        self.stdout.write(f"Observations created: {run.observations_created}")
