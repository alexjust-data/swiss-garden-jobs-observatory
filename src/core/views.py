"""Core views for baseline operational checks."""

from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health_check(request):
    del request
    return JsonResponse({"status": "ok", "service": "swiss-garden-jobs-observatory"})
