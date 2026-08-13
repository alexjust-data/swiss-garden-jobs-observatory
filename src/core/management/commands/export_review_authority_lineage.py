from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.review_authority_lineage import (
    ReviewAuthorityLineageError,
    export_package,
    verify_registry_against_merged_governance,
)


class Command(BaseCommand):
    help = "Export a verified GATE-011G-C1 authority package from a read-only source snapshot"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--package-output", required=True)
        parser.add_argument("--registry-output", required=True)
        parser.add_argument(
            "--governance-document",
            default="docs/day0/gate_011e_critical_review_resolution_v0_1.md",
        )

    def handle(self, *args: object, **options: object) -> None:
        try:
            package, registry = export_package()
            verify_registry_against_merged_governance(
                registry, Path(str(options["governance_document"]))
            )
        except ReviewAuthorityLineageError as exc:
            raise CommandError(str(exc)) from exc
        package_path = Path(str(options["package_output"]))
        registry_path = Path(str(options["registry_output"]))
        package_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        package_path.write_text(
            json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        registry_path.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(
            " ".join(
                (
                    f"package_sha256={package['package_sha256']}",
                    f"snapshot={package['manifest']['source_snapshot_fingerprint']}",
                    f"green={len(registry['green_human_decisions'])}",
                    f"dedup={len(registry['dedup_human_decisions'])}",
                )
            )
        )
