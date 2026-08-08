from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from collectors.winterthur import WinterthurCollector, WinterthurCollectorError
from observations.models import GreenRelevanceAssessment


class Command(BaseCommand):
    help = "Run a targeted or full manual Winterthur collection."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--posting-id", action="append", dest="posting_ids")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--full-snapshot", action="store_true")
        parser.add_argument("--delay-seconds", type=float, default=1.0)
        parser.add_argument("--acknowledge-automation-review", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        posting_ids = set(options["posting_ids"] or []) or None
        full = bool(options["full_snapshot"])
        if full and posting_ids:
            raise CommandError("--full-snapshot is incompatible with --posting-id")
        if full and options["limit"] is not None:
            raise CommandError("--full-snapshot is incompatible with --limit")
        if not full and not posting_ids:
            raise CommandError("specify --posting-id or --full-snapshot")
        try:
            run = WinterthurCollector(delay_seconds=options["delay_seconds"]).collect(
                posting_ids=posting_ids,
                limit=options["limit"],
                full_snapshot=full,
                acknowledge_automation_review=bool(options["acknowledge_automation_review"]),
            )
        except (WinterthurCollectorError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        counts = {
            result: GreenRelevanceAssessment.objects.filter(
                posting_observation__collection_run=run, result=result
            ).count()
            for result in ("GREEN_CONFIRMED", "REVIEW", "NOT_GREEN")
        }
        self.stdout.write(self.style.SUCCESS("Winterthur collection complete"))
        for label, value in (
            ("Run", run.id),
            ("Run scope", run.run_scope),
            ("Status", run.status),
            ("Listing total discovered", run.listing_total_discovered),
            ("Postings in scope", run.postings_in_scope),
            ("Details fetched", run.details_fetched),
            ("Observations created", run.observations_created),
            ("Green assessments created", run.green_assessments_created),
            ("Negative observations created", run.negative_observations_created),
            ("Source health", run.source_health_status),
            ("GREEN_CONFIRMED", counts["GREEN_CONFIRMED"]),
            ("REVIEW", counts["REVIEW"]),
            ("NOT_GREEN", counts["NOT_GREEN"]),
            ("Snapshot complete", run.snapshot_complete),
        ):
            self.stdout.write(f"{label}: {value}")
