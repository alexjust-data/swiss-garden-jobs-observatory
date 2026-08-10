from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.dateparse import parse_datetime

from dashboard.services import DashboardBuildError, build_dashboard_snapshot
from premium_segments.models import PremiumSegmentRun
from vacancies.models import DedupRun


class Command(BaseCommand):
    help = "Build an immutable, network-free dashboard snapshot"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--as-of", required=True)
        parser.add_argument("--dedup-run", required=True)
        parser.add_argument("--premium-run", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        as_of = parse_datetime(options["as_of"])
        if as_of is None or as_of.tzinfo is None:
            raise CommandError("--as-of must be an ISO-8601 timestamp with timezone")
        try:
            dedup_run = DedupRun.objects.get(pk=options["dedup_run"])
            premium_run = PremiumSegmentRun.objects.get(pk=options["premium_run"])
            snapshot, reused = build_dashboard_snapshot(
                as_of=as_of, dedup_run=dedup_run, premium_run=premium_run
            )
        except (DedupRun.DoesNotExist, PremiumSegmentRun.DoesNotExist, DashboardBuildError):
            raise CommandError(
                "dashboard snapshot build failed; inspect governed run evidence"
            ) from None
        summary = {
            "snapshot_id": str(snapshot.pk),
            "as_of": snapshot.as_of.isoformat(),
            "input_fingerprint": snapshot.input_fingerprint,
            "dedup_run_id": str(snapshot.dedup_run.pk),
            "premium_run_id": str(snapshot.premium_run.pk),
            "total_vacancy_states": snapshot.total_vacancy_states,
            "public_green_confirmed": snapshot.public_green_eligible_count,
            "mappable": snapshot.mappable_vacancy_count,
            "unmappable": snapshot.unmappable_vacancy_count,
            "review_not_public": snapshot.review_not_public_count,
            "private_location_protected": snapshot.private_location_protected_count,
            "dedup_review_queue_size": snapshot.dedup_review_count,
            "exact_replay_reused": reused,
        }
        self.stdout.write(json.dumps(summary, sort_keys=True))
