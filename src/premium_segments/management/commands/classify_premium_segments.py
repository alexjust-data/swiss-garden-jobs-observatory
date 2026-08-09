from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.dateparse import parse_datetime

from premium_segments.classifier import run_classification
from premium_segments.models import PremiumSegmentAssessment


class Command(BaseCommand):
    help = "Classify premium/private segments from stored PIT source evidence"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--as-of", required=True)

    def handle(self, *args: object, **options: object) -> None:
        as_of = parse_datetime(str(options["as_of"]))
        if as_of is None or as_of.tzinfo is None:
            raise CommandError("--as-of must be an ISO-8601 timestamp with timezone")
        try:
            run, reused = run_classification(as_of)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        summary = {
            "run_id": str(run.pk),
            "as_of": run.as_of.isoformat(),
            "input_fingerprint": run.input_fingerprint,
            "classifier_version": run.classifier_version,
            "taxonomy_version": run.taxonomy_version,
            "taxonomy_sha256": run.taxonomy_sha256,
            "observations_considered": run.observations_considered,
            "green_confirmed_eligible": run.green_confirmed_eligible,
            "CLASSIFIED": run.classified_count,
            "REVIEW": run.review_count,
            "NO_SUFFICIENT_EVIDENCE": run.no_sufficient_evidence_count,
            "SKIPPED_NOT_GREEN": run.skipped_not_green_count,
            "PRIVATE_RESIDENTIAL_STANDARD": run.private_residential_standard_count,
            "PRIVATE_RESIDENTIAL_PREMIUM": run.private_residential_premium_count,
            "PRIVATE_ESTATE_DIRECT": run.private_estate_direct_count,
            "UNKNOWN": run.unknown_count,
            "prohibited_inference_only": run.prohibited_inference_only_count,
            "exact_replay_reused": reused,
        }
        self.stdout.write(json.dumps(summary, sort_keys=True))
        positives = PremiumSegmentAssessment.objects.filter(
            run=run,
            segment__in=[
                PremiumSegmentAssessment.Segment.PRIVATE_RESIDENTIAL_PREMIUM,
                PremiumSegmentAssessment.Segment.PRIVATE_ESTATE_DIRECT,
            ],
            assessment_status=PremiumSegmentAssessment.Status.CLASSIFIED,
        ).select_related("posting_observation__source")
        for assessment in positives:
            self.stdout.write(
                json.dumps(
                    {
                        "observation_id": str(assessment.posting_observation_id),
                        "source_id": assessment.posting_observation.source_id,
                        "source_posting_id": assessment.posting_observation.source_posting_id,
                        "segment": assessment.segment,
                        "signal_ids": assessment.matched_signal_ids,
                        "evidence_scopes": assessment.matched_fields_and_scopes,
                        "method": assessment.method,
                    },
                    sort_keys=True,
                )
            )
