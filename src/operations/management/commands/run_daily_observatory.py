from __future__ import annotations

import json
import uuid
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from operations.models import ObservatoryCycle
from operations.services import ObservatoryOperationError, cycle_summary, run_cycle

EXIT_BY_STATUS = {
    ObservatoryCycle.Status.ABORTED_CONCURRENCY: 2,
    ObservatoryCycle.Status.FAILED_COLLECTION: 3,
    ObservatoryCycle.Status.FAILED_COMPLETENESS: 3,
    ObservatoryCycle.Status.FAILED_CONTINUITY: 4,
    ObservatoryCycle.Status.FAILED_DEDUP: 5,
    ObservatoryCycle.Status.FAILED_PREMIUM: 6,
    ObservatoryCycle.Status.FAILED_DASHBOARD: 7,
    ObservatoryCycle.Status.FAILED_READINESS: 8,
}


class Command(BaseCommand):
    help = "Run one governed daily Observatory Cycle."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--cycle-id")
        parser.add_argument(
            "--trigger", choices=[item.value for item in ObservatoryCycle.Trigger], default="MANUAL"
        )
        parser.add_argument("--resume", action="store_true")
        parser.add_argument("--delay-seconds", type=float, default=1.0)
        parser.add_argument("--timeout-seconds", type=int, default=14_400)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args: Any, **options: Any) -> None:
        raw_id = options.get("cycle_id")
        try:
            cycle_id = uuid.UUID(raw_id) if raw_id else None
        except ValueError as exc:
            raise CommandError("--cycle-id must be a UUID") from exc
        try:
            result = run_cycle(
                cycle_id=cycle_id,
                trigger=options["trigger"],
                resume=bool(options["resume"]),
                delay_seconds=options["delay_seconds"],
                timeout_seconds=options["timeout_seconds"],
            )
        except ObservatoryOperationError as exc:
            raise CommandError(f"{exc.code}: {exc}") from exc
        payload = cycle_summary(result.cycle, reused=result.reused)
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
        else:
            for key in (
                "cycle_id",
                "status",
                "operational_health",
                "cutoff",
                "sources_selected",
                "source_successful",
                "blocked_selected",
                "dedup_run",
                "premium_run",
                "dashboard_snapshot",
                "readiness_assessment",
            ):
                self.stdout.write(f"{key}: {payload[key]}")
        exit_code = EXIT_BY_STATUS.get(result.cycle.status, 0)
        if exit_code:
            raise SystemExit(exit_code)
