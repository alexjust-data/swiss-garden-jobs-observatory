from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swiss_garden_jobs.settings")

import django  # noqa: E402

django.setup()

from core.production_acceptance import (  # noqa: E402
    OPERATION_GEOSPATIAL,
    ProductionAcceptanceError,
    _assert_output_scope,
    run_geospatial_acceptance,
    write_report,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Capture mechanical H2 evidence for one bounded operational execution."
    )
    result.add_argument("--operation", required=True, choices=[OPERATION_GEOSPATIAL])
    result.add_argument("--premium-run", required=True, help="Exact PremiumSegmentRun UUID")
    result.add_argument("--expected-database", required=True)
    result.add_argument("--execute", action="store_true", help="Execute operation and exact retry")
    result.add_argument(
        "--allow-operational",
        action="store_true",
        help="Acknowledge the separately authorized operational mutation boundary",
    )
    result.add_argument(
        "--verify-raw-bytes",
        action="store_true",
        help="Read and verify every governed RawArtifact byte object",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / ".production-acceptance",
    )
    result.add_argument("--json", action="store_true", help="Print canonical report JSON")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        output_dir = _assert_output_scope(arguments.output_dir)
        report = run_geospatial_acceptance(
            premium_run_id=arguments.premium_run,
            expected_database=arguments.expected_database,
            execute=arguments.execute,
            allow_operational=arguments.allow_operational,
            verify_raw_bytes=arguments.verify_raw_bytes,
        )
        json_path, text_path = write_report(report, output_dir)
    except ProductionAcceptanceError as exc:
        print(f"H2_CONFIGURATION_ERROR: {exc}", file=sys.stderr)
        return 2
    if arguments.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(text_path.read_text(encoding="utf-8"), end="")
        print(f"JSON: {json_path}")
        print(f"Text: {text_path}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
