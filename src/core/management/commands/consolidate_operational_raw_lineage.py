from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.raw_lineage import (
    RawLineageError,
    consolidate_manifest,
    load_json,
    parse_source_roots,
)


class Command(BaseCommand):
    help = "Preflight or apply the repository-designated operational RAW lineage manifest."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--source-root", action="append", required=True)
        parser.add_argument("--destination-root", required=True)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--apply", action="store_true")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            manifest = load_json(Path(str(options["manifest"])))
            roots = parse_source_roots(str(value) for value in options["source_root"])
            destination = Path(str(options["destination_root"]))
            result = consolidate_manifest(
                manifest,
                roots,
                destination,
                dry_run=bool(options["dry_run"]),
            )
        except RawLineageError as exc:
            raise CommandError(str(exc)) from exc
        payload = result.to_dict()
        if options["json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            return
        for key, value in payload.items():
            self.stdout.write(f"{key}: {value}")
