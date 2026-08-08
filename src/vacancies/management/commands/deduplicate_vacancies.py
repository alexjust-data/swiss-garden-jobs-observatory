from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from vacancies.engine import run_deduplication, run_summary
from vacancies.models import DedupDecision
from vacancies.normalizer import DEDUP_VERSION


class Command(BaseCommand):
    help = "Derive point-in-time Vacancy identities from immutable Posting evidence."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--as-of")
        parser.add_argument("--dedup-version", default=DEDUP_VERSION)

    def handle(self, *args: Any, **options: Any) -> None:
        as_of = self._as_of(options.get("as_of"))
        try:
            run, reused = run_deduplication(as_of, options["dedup_version"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        summary = run_summary(run)
        self.stdout.write(f"dedup run ID: {run.pk}")
        self.stdout.write(f"dedup version: {run.dedup_version}")
        self.stdout.write(f"normalizer version: {run.normalizer_version}")
        self.stdout.write(f"as_of: {run.as_of.isoformat()}")
        self.stdout.write(f"input fingerprint: {run.input_fingerprint}")
        self.stdout.write(f"idempotent reuse: {str(reused).lower()}")
        for field in (
            "postings_considered",
            "candidate_pairs",
            "hard_key_merges",
            "rule_auto_merges",
            "review_pairs",
            "keep_separate_pairs",
            "hard_barrier_pairs",
            "vacancies_created",
            "episodes_created",
        ):
            self.stdout.write(f"{field}: {getattr(run, field)}")
        for key, value in summary.items():
            self.stdout.write(f"{key}: {json.dumps(value, sort_keys=True)}")
        for decision in DedupDecision.objects.filter(
            dedup_run=run,
            outcome__in=[DedupDecision.Outcome.AUTO_MERGE, DedupDecision.Outcome.REVIEW],
        ).select_related("posting_a__source", "posting_b__source"):
            self.stdout.write(
                json.dumps(
                    {
                        "decision_id": str(decision.pk),
                        "outcome": decision.outcome,
                        "method": decision.method,
                        "score": str(decision.score),
                        "posting_a": [
                            decision.posting_a.source.source_id,
                            decision.posting_a.source_posting_id,
                        ],
                        "posting_b": [
                            decision.posting_b.source.source_id,
                            decision.posting_b.source_posting_id,
                        ],
                        "feature_scores": decision.feature_scores,
                        "hard_barriers": decision.hard_barriers,
                    },
                    sort_keys=True,
                )
            )

    @staticmethod
    def _as_of(raw: str | None) -> datetime:
        if raw is None:
            return timezone.now()
        parsed = parse_datetime(raw)
        if parsed is None or timezone.is_naive(parsed):
            raise CommandError("--as-of must be an ISO-8601 timezone-aware timestamp")
        return parsed
