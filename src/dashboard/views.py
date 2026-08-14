from __future__ import annotations

import math
from datetime import date
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .models import DashboardSnapshot, DashboardVacancyRecord
from .services import DASHBOARD_VERSION, SCOPE_NOTICE


class FilterError(ValueError):
    pass


def _snapshot(snapshot_id: UUID | None = None) -> DashboardSnapshot:
    query = DashboardSnapshot.objects.select_related("dedup_run", "premium_run").filter(
        dashboard_version=DASHBOARD_VERSION
    )
    if snapshot_id is None:
        item = query.order_by("-as_of", "-input_fingerprint", "-pk").first()
        if item is None:
            raise Http404("No dashboard snapshot is available")
        return item
    return get_object_or_404(query, pk=snapshot_id)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def snapshot_metadata(snapshot: DashboardSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": str(snapshot.pk),
        "as_of": snapshot.as_of.isoformat(),
        "dashboard_version": snapshot.dashboard_version,
        "dedup_run_id": str(snapshot.dedup_run.pk),
        "premium_run_id": str(snapshot.premium_run.pk),
        "scope_notice": SCOPE_NOTICE,
        "headline_market_state": "SEE_EXACT_DAY0_ASSESSMENT",
        "day0_authorization_endpoint": "/api/v1/day0/readiness/current/",
        "counts": {
            "public_green_confirmed": snapshot.public_green_eligible_count,
            "mappable": snapshot.mappable_vacancy_count,
            "unmappable": snapshot.unmappable_vacancy_count,
        },
        "quality": {
            "published_date_coverage_ratio": _ratio(
                snapshot.known_publication_date_count,
                snapshot.public_green_eligible_count,
            ),
            "safe_geocoded_ratio": _ratio(
                snapshot.mappable_vacancy_count,
                snapshot.public_green_eligible_count,
            ),
            "dedup_review_queue_size": snapshot.dedup_review_count,
            "denominator": "public_green_confirmed",
        },
    }


def _date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FilterError(f"{name} must be YYYY-MM-DD") from exc


def _public_records(snapshot: DashboardSnapshot) -> QuerySet[DashboardVacancyRecord]:
    return DashboardVacancyRecord.objects.select_related(
        "snapshot", "canonical_posting", "canonical_observation"
    ).filter(
        snapshot=snapshot,
        visibility_status=DashboardVacancyRecord.VisibilityStatus.PUBLIC_GREEN_CONFIRMED,
    )


FILTER_KEYS = {
    "status",
    "canton",
    "municipality",
    "source",
    "segment",
    "precision",
    "mapping",
    "published_from",
    "published_to",
    "first_seen_from",
    "first_seen_to",
    "q",
}


def filtered_records(
    request: HttpRequest,
    snapshot: DashboardSnapshot,
    *,
    allow_pagination: bool = False,
) -> QuerySet[DashboardVacancyRecord]:
    query = _public_records(snapshot)
    params = request.GET
    allowed = FILTER_KEYS | ({"page", "page_size"} if allow_pagination else set())
    unknown = set(params) - allowed
    if unknown:
        raise FilterError(f"unknown filter: {sorted(unknown)[0]}")
    repeated = [key for key, values in params.lists() if len(values) > 1]
    if repeated:
        raise FilterError(f"repeated filter: {sorted(repeated)[0]}")
    for key in FILTER_KEYS:
        if len(params.get(key, "")) > 200:
            raise FilterError(f"{key} is too long")
    enums = {
        "status": {"ACTIVE", "CLOSED_OBSERVED"},
        "segment": {
            "PRIVATE_RESIDENTIAL_STANDARD",
            "PRIVATE_RESIDENTIAL_PREMIUM",
            "PRIVATE_ESTATE_DIRECT",
            "UNKNOWN",
        },
        "precision": {
            "EXACT_WORK_ADDRESS",
            "POSTCODE",
            "MUNICIPALITY",
            "DISTRICT_OR_REGION",
            "CANTON",
            "REMOTE_OR_MULTIPLE",
            "UNKNOWN",
        },
        "mapping": {"MAPPABLE", "UNMAPPABLE"},
    }
    for key, values in enums.items():
        enum_value = params.get(key, "")
        if enum_value and enum_value not in values:
            raise FilterError(f"invalid {key}")
    if value := params.get("status"):
        query = query.filter(vacancy_status=value)
    if value := params.get("canton"):
        if len(value) != 2 or not value.isalpha():
            raise FilterError("canton must be a two-letter code")
        query = query.filter(canton_code=value.upper())
    if value := params.get("municipality"):
        query = query.filter(municipality_name__iexact=value[:100])
    if value := params.get("source"):
        query = query.filter(canonical_observation__source_id=value[:40])
    if value := params.get("segment"):
        query = query.filter(premium_segment=value)
    if value := params.get("precision"):
        query = query.filter(location_precision=value)
    if value := params.get("mapping"):
        if value == "MAPPABLE":
            query = query.filter(mapping_status=DashboardVacancyRecord.MappingStatus.MAPPABLE)
        else:
            query = query.exclude(mapping_status=DashboardVacancyRecord.MappingStatus.MAPPABLE)
    if value := params.get("published_from"):
        query = query.filter(source_published_date__gte=_date(value, "published_from"))
    if value := params.get("published_to"):
        query = query.filter(source_published_date__lte=_date(value, "published_to"))
    if value := params.get("first_seen_from"):
        query = query.filter(first_seen_at__date__gte=_date(value, "first_seen_from"))
    if value := params.get("first_seen_to"):
        query = query.filter(first_seen_at__date__lte=_date(value, "first_seen_to"))
    for start, end in (
        ("published_from", "published_to"),
        ("first_seen_from", "first_seen_to"),
    ):
        if params.get(start) and params.get(end):
            if _date(params[start], start) > _date(params[end], end):
                raise FilterError(f"{start} must not be after {end}")
    if value := params.get("q"):
        value = value.strip()[:100]
        query = query.filter(Q(title__icontains=value) | Q(employer__icontains=value))
    return query.order_by("-first_seen_at", "run_vacancy_key")


def serialize_record(record: DashboardVacancyRecord, *, detail: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {
        "run_vacancy_key": record.run_vacancy_key,
        "canonical_posting_id": str(record.canonical_posting.pk),
        "posting_observation_id": str(record.canonical_observation.pk),
        "title": record.title,
        "employer": record.employer,
        "status": record.vacancy_status,
        "source_publication_date": (
            record.source_published_date.isoformat() if record.source_published_date else None
        ),
        "published_at_precision": record.published_at_precision,
        "published_at_parse_method": record.published_at_parse_method,
        "first_observed": record.first_seen_at.isoformat(),
        "last_observed": record.last_seen_at.isoformat(),
        "closed_observed": (
            record.closed_observed_at.isoformat() if record.closed_observed_at else None
        ),
        "municipality": record.municipality_name or None,
        "canton": record.canton_code or None,
        "location_precision": record.location_precision,
        "privacy_display_level": record.privacy_display_level or None,
        "approximate_location": record.privacy_context != "PUBLIC_OR_NON_RESIDENTIAL",
        "mapping_status": record.mapping_status,
        "segment": record.premium_segment,
        "premium_assessment_status": record.premium_assessment_status,
        "source_name": record.source_name,
        "source_type": record.source_type,
        "source_link_status": record.source_link_status,
        "source_link_label": record.visible_link_label or None,
        "external_url": record.selected_external_url or None,
        "detail_url": reverse(
            "dashboard:posting_detail", kwargs={"posting_id": record.canonical_posting.pk}
        )
        + f"?snapshot={record.snapshot.pk}",
        "workload": record.workload or "NOT_REPORTED_BY_SOURCE",
        "positions_count": record.positions_count,
        "multi_hire_possible": record.multi_hire_possible,
        "episode_number": record.episode_number,
        "salary_availability": "NOT_IMPLEMENTED_IN_CURRENT_GATE",
    }
    if detail:
        value["description"] = record.safe_description
        value["source_provenance"] = record.source_provenance
        value["dashboard_snapshot_id"] = str(record.snapshot.pk)
    return value


def jobs_page(request: HttpRequest) -> HttpResponse:
    try:
        current = _snapshot()
    except Http404:
        current = None
    return render(
        request,
        "dashboard/jobs.html",
        {
            "snapshot": current,
            "scope_notice": SCOPE_NOTICE,
            "map_style_url": settings.DASHBOARD_MAP_STYLE_URL,
            "map_attribution": settings.DASHBOARD_MAP_ATTRIBUTION,
            "map_provider": settings.DASHBOARD_MAP_PROVIDER,
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        },
    )


def current_snapshot(request: HttpRequest) -> JsonResponse:
    return JsonResponse(snapshot_metadata(_snapshot()))


def snapshot_detail(request: HttpRequest, snapshot_id: UUID) -> JsonResponse:
    return JsonResponse(snapshot_metadata(_snapshot(snapshot_id)))


def vacancy_list(request: HttpRequest, snapshot_id: UUID) -> JsonResponse:
    snapshot = _snapshot(snapshot_id)
    try:
        query = filtered_records(request, snapshot, allow_pagination=True)
        page_size = int(request.GET.get("page_size", "25"))
        page_number = int(request.GET.get("page", "1"))
        if page_size < 1 or page_size > 100 or page_number < 1:
            raise FilterError("invalid pagination")
    except (FilterError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    paginator = Paginator(query, page_size)
    try:
        page = paginator.page(page_number)
    except EmptyPage:
        return JsonResponse({"error": "page out of range"}, status=400)
    return JsonResponse(
        {
            **snapshot_metadata(snapshot),
            "pagination": {
                "page": page.number,
                "page_size": page_size,
                "total": paginator.count,
                "pages": paginator.num_pages,
            },
            "results": [serialize_record(item) for item in page.object_list],
        }
    )


def vacancy_geojson(request: HttpRequest, snapshot_id: UUID) -> JsonResponse:
    snapshot = _snapshot(snapshot_id)
    try:
        query = filtered_records(request, snapshot).filter(
            mapping_status=DashboardVacancyRecord.MappingStatus.MAPPABLE
        )
        records = list(query[:5001])
        truncated = len(records) > 5000
        records = records[:5000]
    except FilterError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    features = []
    for record in records:
        latitude = record.public_display_latitude
        longitude = record.public_display_longitude
        if (
            latitude is None
            or longitude is None
            or not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not (-90 <= latitude <= 90 and -180 <= longitude <= 180)
            or record.location_resolution_status != "RESOLVED"
            or record.privacy_display_level == "HIDDEN"
        ):
            continue
        features.append(
            {
                "type": "Feature",
                "id": record.run_vacancy_key,
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        record.public_display_longitude,
                        record.public_display_latitude,
                    ],
                },
                "properties": serialize_record(record),
            }
        )
    return JsonResponse(
        {
            "type": "FeatureCollection",
            "metadata": {
                **snapshot_metadata(snapshot),
                "feature_limit": 5000,
                "truncated": truncated,
            },
            "features": features,
        }
    )


def vacancy_detail_api(
    request: HttpRequest, snapshot_id: UUID, run_vacancy_key: str
) -> JsonResponse:
    snapshot = _snapshot(snapshot_id)
    record = get_object_or_404(_public_records(snapshot), run_vacancy_key=run_vacancy_key)
    return JsonResponse(
        {**snapshot_metadata(snapshot), "record": serialize_record(record, detail=True)}
    )


def posting_detail(request: HttpRequest, posting_id: UUID) -> HttpResponse:
    raw_snapshot = request.GET.get("snapshot", "")
    try:
        snapshot_id = UUID(raw_snapshot)
    except ValueError as exc:
        raise Http404("A valid snapshot is required") from exc
    snapshot = _snapshot(snapshot_id)
    record = get_object_or_404(_public_records(snapshot), canonical_posting_id=posting_id)
    return render(request, "dashboard/_job_detail.html", {"record": record, "snapshot": snapshot})
