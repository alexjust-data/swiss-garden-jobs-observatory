from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser

from vacancies.engine import CONFIGURATION
from vacancies.models import DedupDecision, DedupReviewItem
from vacancies.review_continuity import (
    DedupContinuityValidationError,
    create_dedup_review_application,
)


class Command(BaseCommand):
    help = "Apply a verified material-identical prior dedup human decision"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--target-review-id", required=True)
        parser.add_argument("--source-human-decision-id", required=True)

    def handle(self, *args: object, **options: object) -> None:
        review = DedupReviewItem.objects.select_related("algorithm_decision__dedup_run").get(
            pk=options["target_review_id"]
        )
        source = DedupDecision.objects.get(pk=options["source_human_decision_id"], method="HUMAN")
        try:
            application, created = create_dedup_review_application(
                target_algorithm_decision=review.algorithm_decision,
                source_human_decision=source,
                configuration=CONFIGURATION,
            )
        except DedupContinuityValidationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"application={application.pk} created={created}")
