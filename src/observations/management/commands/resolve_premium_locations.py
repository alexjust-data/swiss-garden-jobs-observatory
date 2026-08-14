from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from observations.geospatial_batch import (
    GeospatialBatchError,
    resolve_premium_run_locations,
)


class Command(BaseCommand):
    help = "Resolve governed locations for the green cohort of one exact PremiumSegmentRun."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--premium-run", required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            result = resolve_premium_run_locations(
                str(options["premium_run"]),
                dry_run=bool(options["dry_run"]),
            )
        except GeospatialBatchError as exc:
            raise CommandError(str(exc)) from exc
        payload = result.to_dict()
        if options["json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            return
        for key, value in payload.items():
            self.stdout.write(f"{key}: {value}")
