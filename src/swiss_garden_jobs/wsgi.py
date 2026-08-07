"""WSGI config for swiss_garden_jobs."""

from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swiss_garden_jobs.settings")

application = get_wsgi_application()
