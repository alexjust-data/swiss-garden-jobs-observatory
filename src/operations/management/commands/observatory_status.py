from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from operations.services import observatory_status


class Command(BaseCommand):
    help = "Inspect persisted Observatory Cycle status without changing evidence."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument("--include-volatile", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        payload = observatory_status(include_volatile=bool(options["include_volatile"]))
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
            return
        latest = payload["latest_cycle"]
        self.stdout.write(f"latest cycle: {latest['cycle_id'] if latest else 'none'}")
        self.stdout.write(f"latest status: {latest['status'] if latest else 'NO_HISTORY'}")
        self.stdout.write(f"last successful cycle: {payload['last_successful_cycle_id'] or 'none'}")
        self.stdout.write(f"PIT cutoff: {payload['pit_cutoff'] or 'none'}")
