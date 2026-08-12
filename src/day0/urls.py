from django.urls import path

from . import views

app_name = "day0"

urlpatterns = [
    path("api/v1/day0/readiness/current/", views.readiness_current, name="current"),
    path(
        "api/v1/day0/readiness/<uuid:assessment_id>/",
        views.readiness_detail,
        name="detail",
    ),
]
