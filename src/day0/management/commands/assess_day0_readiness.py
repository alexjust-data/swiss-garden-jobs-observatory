from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.dateparse import parse_datetime

from dashboard.models import DashboardSnapshot
from day0.services import Day0ContractError, assess_day0_readiness, readiness_summary
from premium_segments.models import PremiumSegmentRun
from vacancies.models import DedupRun


class Command(BaseCommand):
    help = "Build or reuse a network-free point-in-time Day-0 readiness assessment."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--as-of", required=True)
        parser.add_argument("--dedup-run", required=True)
        parser.add_argument("--premium-run", required=True)
        parser.add_argument("--dashboard-snapshot", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        as_of = parse_datetime(options["as_of"])
        if as_of is None or as_of.tzinfo is None:
            raise CommandError("--as-of must be an ISO-8601 timezone-aware timestamp")
        try:
            assessment, reused = assess_day0_readiness(
                as_of=as_of,
                dedup_run=DedupRun.objects.get(pk=options["dedup_run"]),
                premium_run=PremiumSegmentRun.objects.get(pk=options["premium_run"]),
                dashboard_snapshot=DashboardSnapshot.objects.get(pk=options["dashboard_snapshot"]),
            )
        except (
            DedupRun.DoesNotExist,
            PremiumSegmentRun.DoesNotExist,
            DashboardSnapshot.DoesNotExist,
        ):
            raise CommandError("One or more governed input IDs do not exist") from None
        except Day0ContractError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(json.dumps(readiness_summary(assessment, reused), sort_keys=True))
