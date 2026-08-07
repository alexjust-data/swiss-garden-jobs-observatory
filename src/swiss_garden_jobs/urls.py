"""URL configuration for Gate-001 baseline."""

from __future__ import annotations

from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", views.health_check),
    path("api/health/", views.health_check),
]
