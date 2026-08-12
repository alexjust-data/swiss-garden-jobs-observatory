from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser

from vacancies.engine import CONFIGURATION
from vacancies.evidence import (
    DEDUP_REVIEW_MATERIAL_VERSION,
    dedup_review_material_fingerprint,
    select_posting_evidence,
)
from vacancies.models import DedupDecision, DedupReviewDecisionApplication, DedupReviewItem


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
        target = review.algorithm_decision
        selected = {
            item.posting_id: item for item in select_posting_evidence(target.dedup_run.as_of)
        }
        left, right = selected[str(target.posting_a_id)], selected[str(target.posting_b_id)]
        material = dedup_review_material_fingerprint(
            left,
            right,
            CONFIGURATION,
            method=target.method,
            score=str(target.score),
            feature_scores=target.feature_scores,
            hard_keys=target.blocking_evidence.get("hard_keys", []),
            hard_barriers=target.hard_barriers,
            algorithm_outcome=target.outcome,
        )
        source_material = source.evidence.get("material_fingerprint")
        if source_material is not None and source_material != material:
            raise CommandError("source decision material differs")
        if {source.posting_a_id, source.posting_b_id} != {
            target.posting_a_id,
            target.posting_b_id,
        }:
            raise CommandError("source decision belongs to another Posting pair")
        application, created = DedupReviewDecisionApplication.objects.get_or_create(
            target_algorithm_decision=target,
            defaults={
                "source_human_decision": source,
                "material_fingerprint": material,
                "fingerprint_version": DEDUP_REVIEW_MATERIAL_VERSION,
                "evidence": {
                    "source_decision_id": str(source.pk),
                    "target_decision_id": str(target.pk),
                },
            },
        )
        if (
            application.source_human_decision_id != source.pk
            or application.material_fingerprint != material
        ):
            raise CommandError("conflicting dedup continuity application")
        self.stdout.write(f"application={application.pk} created={created}")
