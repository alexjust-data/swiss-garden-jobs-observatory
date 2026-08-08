from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from vacancies.review import resolve_review


class Command(BaseCommand):
    help = "Resolve a pending deduplication review with immutable human evidence."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--review-id", required=True)
        action = parser.add_mutually_exclusive_group(required=True)
        action.add_argument("--merge", action="store_true")
        action.add_argument("--keep-separate", action="store_true")
        parser.add_argument("--reason", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            decision = resolve_review(
                options["review_id"], merge=options["merge"], reason=options["reason"]
            )
        except (ValueError, LookupError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"human decision: {decision.pk} {decision.outcome}")
