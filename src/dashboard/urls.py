from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("jobs/", views.jobs_page, name="jobs"),
    path("postings/<uuid:posting_id>/", views.posting_detail, name="posting_detail"),
    path("api/v1/dashboard/snapshots/current/", views.current_snapshot, name="current"),
    path("api/v1/dashboard/snapshots/<uuid:snapshot_id>/", views.snapshot_detail, name="snapshot"),
    path(
        "api/v1/dashboard/snapshots/<uuid:snapshot_id>/vacancies/",
        views.vacancy_list,
        name="vacancies",
    ),
    path(
        "api/v1/dashboard/snapshots/<uuid:snapshot_id>/vacancies.geojson",
        views.vacancy_geojson,
        name="geojson",
    ),
    path(
        "api/v1/dashboard/snapshots/<uuid:snapshot_id>/vacancies/<str:run_vacancy_key>/",
        views.vacancy_detail_api,
        name="vacancy_detail_api",
    ),
]
