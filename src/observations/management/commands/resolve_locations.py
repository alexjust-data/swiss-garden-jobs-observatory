from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from observations.geospatial import GeospatialResolver
from observations.models import GeocodingReviewItem, PostingObservation
from sources.models import Source


class Command(BaseCommand):
    help = "Resolve existing ACTIVE observations without recollecting the source."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--source-id", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        source_id = str(options["source_id"])
        if not Source.objects.filter(pk=source_id).exists():
            raise CommandError(f"unknown source: {source_id}")
        observations = (
            PostingObservation.objects.filter(source_id=source_id, observation_status="ACTIVE")
            .select_related("source", "municipality")
            .order_by("observed_at", "pk")
        )
        resolver = GeospatialResolver()
        for observation in observations.iterator():
            resolver.resolve(observation)
        stats = resolver.stats
        review_size = GeocodingReviewItem.objects.filter(
            resolver_version=resolver.resolver_version,
            review_status="PENDING",
            posting_observation__source_id=source_id,
        ).count()
        values = (
            ("Resolver version", resolver.resolver_version),
            ("Observations considered", stats.observations_considered),
            ("Already resolved", stats.already_resolved),
            ("Resolved", stats.resolved),
            ("Review", stats.review),
            ("Unresolved", stats.unresolved),
            ("Unique geocoder requests", len(stats.unique_geocoder_requests)),
            ("Cache hits", stats.cache_hits),
            ("Network requests", stats.network_requests),
            ("Privacy generalization count", stats.privacy_generalizations),
            ("Review queue size", review_size),
        )
        for label, value in values:
            self.stdout.write(f"{label}: {value}")
        self.stdout.write(
            f"Location precision distribution: {dict(sorted(stats.precision_distribution.items()))}"
        )
        coordinate_distribution = dict(
            sorted(stats.coordinate_source_distribution.items())
        )
        self.stdout.write(
            f"Coordinate source distribution: {coordinate_distribution}"
        )
