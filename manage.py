#!/usr/bin/env python
"""Django administrative entrypoint for Swiss Garden Jobs Observatory."""

import os
import sys
from pathlib import Path


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swiss_garden_jobs.settings")
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root / "src"))

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Install dependencies with: "
            "python -m pip install -r requirements-dev.txt"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
