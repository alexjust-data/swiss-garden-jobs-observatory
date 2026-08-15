from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.raw_lineage import (
    RawLineageError,
    build_designation,
    capture_manifest,
    parse_source_roots,
    write_json,
)


class Command(BaseCommand):
    help = "Build one read-only GATE-010-C4 RAW lineage manifest candidate."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--source-root", action="append", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--designation-output")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            roots = parse_source_roots(str(value) for value in options["source_root"])
            manifest = capture_manifest(roots)
            output = Path(str(options["output"]))
            write_json(output, manifest)
            designation_output_value = options.get("designation_output")
            if designation_output_value:
                write_json(
                    Path(str(designation_output_value)),
                    build_designation(manifest),
                )
        except RawLineageError as exc:
            raise CommandError(str(exc)) from exc
        payload = {
            "manifest": str(output),
            "manifest_sha256": manifest["manifest_sha256"],
            "database_snapshot_fingerprint": manifest["database_snapshot_fingerprint"],
            "raw_inventory_fingerprint": manifest["raw_inventory_fingerprint"],
            "source_inventory_fingerprint": manifest["source_inventory_fingerprint"],
            "object_count": manifest["object_count"],
            "aggregate_byte_count": manifest["aggregate_byte_count"],
            "representation_counts": manifest["representation_counts"],
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            return
        for key, value in payload.items():
            self.stdout.write(f"{key}: {value}")
