from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.dateparse import parse_datetime

from observations.models import (
    GreenRelevanceAssessment,
    GreenRelevanceReviewDecision,
    GreenRelevanceReviewDecisionApplication,
)
from observations.review import (
    GREEN_REVIEW_GOVERNANCE_VERSION,
    apply_materially_identical_green_decision,
)
from observations.review_continuity import green_review_material_fingerprint


class Command(BaseCommand):
    help = "Apply exact material-identical prior green human decisions to later assessments"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--target-as-of", required=True)

    def handle(self, *args: object, **options: object) -> None:
        as_of = parse_datetime(str(options["target_as_of"]))
        if as_of is None:
            raise CommandError("--target-as-of must be ISO-8601")
        created = reused = unmatched = 0
        targets = GreenRelevanceAssessment.objects.filter(
            result="REVIEW", created_at__lte=as_of
        ).select_related("posting_observation__posting", "posting_observation__raw_artifact")
        for target in targets:
            if GreenRelevanceReviewDecision.objects.filter(
                assessment=target, governance_version=GREEN_REVIEW_GOVERNANCE_VERSION
            ).exists():
                continue
            before = GreenRelevanceReviewDecisionApplication.objects.filter(
                target_assessment=target, governance_version=GREEN_REVIEW_GOVERNANCE_VERSION
            ).exists()
            target_fp = green_review_material_fingerprint(
                target, governance_version=GREEN_REVIEW_GOVERNANCE_VERSION
            )
            source = None
            decisions = GreenRelevanceReviewDecision.objects.filter(
                assessment__posting_observation__posting_id=target.posting_observation.posting_id,
                governance_version=GREEN_REVIEW_GOVERNANCE_VERSION,
                created_at__lte=as_of,
                reviewed_at__lte=as_of,
            ).select_related("assessment__posting_observation__raw_artifact")
            for candidate in decisions:
                if (
                    green_review_material_fingerprint(
                        candidate.assessment,
                        governance_version=GREEN_REVIEW_GOVERNANCE_VERSION,
                    )
                    == target_fp
                ):
                    source = candidate
                    break
            if source is None:
                unmatched += 1
                continue
            apply_materially_identical_green_decision(
                target_assessment=target, source_decision=source
            )
            if before:
                reused += 1
            else:
                created += 1
        self.stdout.write(
            f"created={created} reused={reused} unmatched={unmatched} "
            f"target_as_of={as_of.isoformat()}"
        )
