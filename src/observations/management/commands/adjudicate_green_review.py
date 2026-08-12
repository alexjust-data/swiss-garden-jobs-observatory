from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from observations.models import GreenRelevanceAssessment, GreenRelevanceReviewDecision
from observations.review import record_green_review_decision


class Command(BaseCommand):
    help = "Append one governed green-relevance review decision."

    def add_arguments(self, parser):
        parser.add_argument("--assessment-id", required=True)
        parser.add_argument(
            "--outcome", required=True, choices=GreenRelevanceReviewDecision.Outcome.values
        )
        parser.add_argument("--reason-code", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--evidence-json", required=True)

    def handle(self, *args, **options):
        try:
            assessment = GreenRelevanceAssessment.objects.get(pk=options["assessment_id"])
            evidence = json.loads(options["evidence_json"])
        except GreenRelevanceAssessment.DoesNotExist as exc:
            raise CommandError("green assessment does not exist") from exc
        except json.JSONDecodeError as exc:
            raise CommandError("evidence-json must be valid JSON") from exc
        if not isinstance(evidence, dict):
            raise CommandError("evidence-json must be a JSON object")
        decision = record_green_review_decision(
            assessment=assessment,
            outcome=options["outcome"],
            reason_code=options["reason_code"],
            reason=options["reason"],
            evidence=evidence,
        )
        self.stdout.write(str(decision.pk))
