"""ASGI config for swiss_garden_jobs."""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swiss_garden_jobs.settings")

application = get_asgi_application()
