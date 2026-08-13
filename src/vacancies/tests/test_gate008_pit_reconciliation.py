from __future__ import annotations

from datetime import UTC, datetime, timedelta
from tempfile import TemporaryDirectory
from typing import Any

from django.test import TestCase

from collectors.pipeline import SharedCollectionPipeline
from collectors.platforms import FetchedPage, FetchRequest, ListingPage
from core.storage import RawObjectStore
from observations.models import Posting, PostingObservation
from sources.models import Source, SourceEndpoint
from vacancies.engine import run_deduplication, run_summary
from vacancies.evidence import select_posting_evidence
from vacancies.models import (
    DedupDecision,
    DedupReviewDecisionApplication,
    DedupReviewItem,
    DedupRunPostingAssignment,
    DedupRunVacancyState,
    PositionCountEvidence,
    Vacancy,
    VacancyEpisode,
    VacancyLifecycleEvent,
    VacancyMembershipEvent,
    VacancyPostingMembership,
    VacancyProjectionState,
)
from vacancies.review import resolve_review
from vacancies.review_continuity import (
    FROZEN_CONFIGURATION,
    DedupContinuityValidationError,
    UnverifiableLegacyHumanDecisionError,
    create_dedup_review_application,
    reconstruct_source_human_material,
)
from vacancies.tests.test_gate008 import Adapter, Clock, Fetcher


class EmptyAdapter(Adapter):
    def parse_listing_page(
        self, page: FetchedPage, request: FetchRequest, source: Source
    ) -> ListingPage:
        return ListingPage([], None, True, 0)


class Gate008PITReconciliationTests(TestCase):
    def source(self, source_id: str, source_type: str = "DIRECT_PUBLIC_EMPLOYER") -> Source:
        domain = f"{source_id.casefold().replace('_', '-')}.test"
        source = Source.objects.create(
            source_id=source_id,
            source_name=source_id,
            domain=domain,
            source_family="OFFICIAL",
            source_type=source_type,
            priority="P0",
            coverage_scope="test",
            canonicality="CANONICAL",
            platform_family="DEDUP_TEST",
            access_method="WEB",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url=f"https://{domain}/",
        )
        SourceEndpoint.objects.create(
            source=source,
            endpoint_role="API",
            platform_family="DEDUP_TEST",
            scheme="https",
            host=domain,
            base_url=f"https://{domain}/",
        )
        return source

    def collect(self, source: Source, adapter: Adapter, when: datetime) -> PostingObservation:
        listing = f"https://{source.domain}/list"
        detail = f"https://{source.domain}/jobs/{adapter.posting_id}"
        pages = {
            listing: FetchedPage(listing, listing, 200, "application/json", b"listing"),
            detail: FetchedPage(detail, detail, 200, "application/json", b"detail"),
        }
        with TemporaryDirectory() as raw:
            SharedCollectionPipeline(
                source_id=source.pk,
                adapter=adapter,
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
                clock=Clock(when),
            ).collect(posting_ids={adapter.posting_id})
        return PostingObservation.objects.get(
            source=source,
            source_posting_id=adapter.posting_id,
            observed_at=when,
        )

    def collect_empty(self, source: Source, when: datetime) -> None:
        listing = f"https://{source.domain}/list"
        pages = {listing: FetchedPage(listing, listing, 200, "application/json", b"empty")}
        with TemporaryDirectory() as raw:
            SharedCollectionPipeline(
                source_id=source.pk,
                adapter=EmptyAdapter("unused"),
                fetcher=Fetcher(pages),
                raw_store=RawObjectStore(raw),
                delay_seconds=0,
                clock=Clock(when),
            ).collect(full_snapshot=True)

    def close_posting(self, source: Source, opened: datetime) -> datetime:
        self.collect_empty(source, opened + timedelta(days=1))
        closed_at = opened + timedelta(days=3)
        self.collect_empty(source, closed_at)
        return closed_at

    @staticmethod
    def state_payload(run_id: object) -> list[tuple[object, ...]]:
        return list(
            DedupRunVacancyState.objects.filter(dedup_run_id=run_id)
            .order_by("run_vacancy_key")
            .values_list(
                "run_vacancy_key",
                "status",
                "canonical_posting_id",
                "first_seen_at",
                "last_seen_at",
                "closed_observed_at",
                "episode_number",
                "positions_count",
                "multi_hire_possible",
            )
        )

    def test_reverse_time_pit_and_historical_summary_stability(self) -> None:
        source = self.source("SRC-PIT-REVERSE")
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = t1 + timedelta(days=1)
        self.collect(source, Adapter("A"), t1)
        self.collect(source, Adapter("B"), t1)
        self.collect(source, Adapter("A", requisition="REQ-SHARED"), t2)
        self.collect(source, Adapter("B", requisition="REQ-SHARED"), t2)

        later_run, _ = run_deduplication(t2)
        assert run_summary(later_run)["effective_vacancies"] == 1
        earlier_run, _ = run_deduplication(t1)
        earlier_summary = run_summary(earlier_run)
        earlier_state = self.state_payload(earlier_run.pk)
        assert earlier_summary["effective_vacancies"] == 2
        assert DedupRunPostingAssignment.objects.filter(dedup_run=earlier_run).count() == 2

        assert run_summary(later_run)["effective_vacancies"] == 1
        assert run_summary(earlier_run) == earlier_summary
        assert self.state_payload(earlier_run.pk) == earlier_state

    def test_forward_time_run_state_remains_field_equivalent(self) -> None:
        source = self.source("SRC-PIT-FORWARD")
        t1 = datetime(2026, 2, 1, tzinfo=UTC)
        t2 = t1 + timedelta(days=1)
        self.collect(source, Adapter("A"), t1)
        self.collect(source, Adapter("B"), t1)
        earlier_run, _ = run_deduplication(t1)
        before = self.state_payload(earlier_run.pk)

        self.collect(source, Adapter("A", requisition="REQ-LATER"), t2)
        self.collect(source, Adapter("B", requisition="REQ-LATER"), t2)
        run_deduplication(t2)

        assert self.state_payload(earlier_run.pk) == before
        assert run_summary(earlier_run)["effective_vacancies"] == 2

    def test_lifecycle_event_changes_input_fingerprint_without_new_active(self) -> None:
        source = self.source("SRC-LIFECYCLE-FINGERPRINT")
        opened = datetime(2026, 3, 1, tzinfo=UTC)
        as_of = opened + timedelta(days=1)
        observation = self.collect(source, Adapter("A"), opened)
        first_run, _ = run_deduplication(as_of)

        self.collect_empty(source, as_of)
        second_run, reused = run_deduplication(as_of)

        assert not reused
        assert second_run.pk != first_run.pk
        assert second_run.input_fingerprint != first_run.input_fingerprint
        selected = select_posting_evidence(as_of)
        assert selected[0].observation_id == str(observation.pk)
        assert selected[0].lifecycle_events[-1]["event_type"] == "DISAPPEARED_PENDING"

    def test_historical_evidence_never_falls_back_to_current_projection(self) -> None:
        source = self.source("SRC-MUTABLE-STATUS")
        observed_at = datetime(2026, 4, 1, tzinfo=UTC)
        self.collect(source, Adapter("A"), observed_at)
        posting = Posting.objects.get(source=source, source_posting_id="A")
        posting.current_status = Posting.LifecycleStatus.CLOSED_OBSERVED
        posting.save(update_fields=["current_status", "updated_at"])

        selected = select_posting_evidence(observed_at)
        assert selected[0].lifecycle_status == "NEW"
        assert selected[0].lifecycle_status != "CLOSED_OBSERVED"

    def test_human_merge_reconciles_state_and_does_not_repeat_review(self) -> None:
        official = self.source("SRC-HUMAN-OFFICIAL")
        aggregator = self.source("SRC-HUMAN-AGG", "GENERAL_AGGREGATOR")
        when = datetime(2026, 5, 1, tzinfo=UTC)
        self.collect(
            official,
            Adapter("A", text="2 Mitarbeitende fuer Gruenpflege"),
            when,
        )
        self.collect(
            aggregator,
            Adapter("B", text="1 Mitarbeitende fuer Gruenpflege"),
            when,
        )
        run, _ = run_deduplication(when)
        historical_summary = run_summary(run)
        review = DedupReviewItem.objects.get(status=DedupReviewItem.Status.PENDING)
        assert Vacancy.objects.filter(merged_into__isnull=True).count() == 2
        assert VacancyEpisode.objects.count() == 2

        human = resolve_review(str(review.pk), merge=True, reason="Controlled same-vacancy fixture")
        review.refresh_from_db()
        effective = Vacancy.objects.get(merged_into__isnull=True)
        memberships = VacancyPostingMembership.objects.filter(vacancy=effective)
        episode = VacancyEpisode.objects.filter(vacancy=effective).get()
        assert memberships.count() == 2
        assert effective.canonical_posting is not None
        assert effective.canonical_posting.source == official
        assert episode.positions_count == 2
        assert PositionCountEvidence.objects.filter(vacancy_episode=episode).count() == 2
        assert DedupDecision.objects.filter(
            pk=review.algorithm_decision.pk,
            outcome=DedupDecision.Outcome.REVIEW,
        ).exists()
        assert human.method == DedupDecision.Method.HUMAN
        assert review.status == DedupReviewItem.Status.MERGED
        assert VacancyMembershipEvent.objects.filter(
            dedup_run=run,
            event_type=VacancyMembershipEvent.EventType.HUMAN_CONFIRM,
        ).exists()

        later_run, _ = run_deduplication(human.created_at + timedelta(seconds=1))
        assert later_run.review_pairs == 0
        assert not DedupReviewItem.objects.filter(status=DedupReviewItem.Status.PENDING).exists()
        assert run_summary(later_run)["effective_vacancies"] == 1
        assert run_summary(run) == historical_summary

    def test_human_keep_separate_does_not_repeat_for_identical_evidence(self) -> None:
        source = self.source("SRC-HUMAN-SEPARATE")
        when = datetime(2026, 5, 2, tzinfo=UTC)
        self.collect(source, Adapter("A"), when)
        self.collect(source, Adapter("B"), when)
        run_deduplication(when)
        review = DedupReviewItem.objects.get(status=DedupReviewItem.Status.PENDING)
        human = resolve_review(str(review.pk), merge=False, reason="Distinct assignments")

        later_run, _ = run_deduplication(human.created_at + timedelta(seconds=1))
        assert later_run.review_pairs == 0
        assert not DedupReviewItem.objects.filter(status=DedupReviewItem.Status.PENDING).exists()
        assert run_summary(later_run)["effective_vacancies"] == 2

    def _active_closed_review_outcome(self, *, merge: bool) -> tuple[int, int, Source]:
        active = self.source(
            f"SRC-ACTIVE-CLOSED-ACTIVE-{'MERGE' if merge else 'KEEP'}",
            "GENERAL_AGGREGATOR",
        )
        closed = self.source(f"SRC-ACTIVE-CLOSED-CLOSED-{'MERGE' if merge else 'KEEP'}")
        opened = datetime(2026, 5, 10, tzinfo=UTC)
        self.collect(active, Adapter("ACTIVE"), opened)
        self.collect(closed, Adapter("CLOSED"), opened)
        cutoff = self.close_posting(closed, opened)

        run, _ = run_deduplication(cutoff)
        review = DedupReviewItem.objects.get(algorithm_decision__dedup_run=run)
        assert review.run_vacancy_state_a is not None
        assert review.run_vacancy_state_b is not None
        assert {review.run_vacancy_state_a.status, review.run_vacancy_state_b.status} == {
            Vacancy.Status.ACTIVE,
            Vacancy.Status.CLOSED_OBSERVED,
        }
        assert run_summary(run)["effective_vacancies"] == 2
        assert run_summary(run)["active_vacancies"] == 1

        resolve_review(
            str(review.pk),
            merge=merge,
            reason="Adversarial ACTIVE/CLOSED identity fixture",
        )
        effective = Vacancy.objects.filter(identity_version="dedup-v0.1", merged_into__isnull=True)
        return effective.count(), effective.filter(current_status="ACTIVE").count(), active

    def test_active_closed_keep_separate_preserves_two_identities_and_one_active(self) -> None:
        effective, active, _ = self._active_closed_review_outcome(merge=False)
        assert (effective, active) == (2, 1)

    def test_active_closed_merge_changes_identity_and_can_close_active_market_state(self) -> None:
        effective, active_count, active_source = self._active_closed_review_outcome(merge=True)
        vacancy = Vacancy.objects.get(identity_version="dedup-v0.1", merged_into__isnull=True)

        assert effective == 1
        assert active_count == 0
        assert vacancy.current_status == Vacancy.Status.CLOSED_OBSERVED
        assert vacancy.canonical_posting is not None
        assert vacancy.canonical_posting.source != active_source

    def _run_repost_case(self, *, gap_days: int, requisition: str | None) -> tuple[Vacancy, int]:
        source = self.source(f"SRC-REPOST-{gap_days}-{requisition or 'NONE'}")
        opened = datetime(2026, 1, 1, tzinfo=UTC)
        common: dict[str, Any] = {
            "title": "Gaertner Gartenunterhalt",
            "employer": "Stadt Test",
            "location": "Winterthur ZH",
            "text": "Pflege der Gruenanlagen",
            "employment_terms": "permanent",
            "requisition": requisition,
        }
        self.collect(source, Adapter("A", **common), opened)
        first_run, _ = run_deduplication(opened)
        original = Vacancy.objects.get(merged_into__isnull=True)
        original_id = original.pk
        closed_at = self.close_posting(source, opened)
        reappeared_at = closed_at + timedelta(days=gap_days)
        self.collect(source, Adapter("B", **common), reappeared_at)
        run_deduplication(reappeared_at)
        effective = Vacancy.objects.filter(merged_into__isnull=True)
        vacancy = effective.order_by("first_seen_at").first()
        assert vacancy is not None
        return vacancy, effective.count() if vacancy.pk == original_id else effective.count()

    def test_repost_new_id_within_90_days_creates_episode_two(self) -> None:
        vacancy, effective_count = self._run_repost_case(gap_days=45, requisition=None)
        assert effective_count == 1
        episode = VacancyEpisode.objects.get(vacancy=vacancy, episode_number=2)
        assert episode.reappearance_gap_days == 45
        assert VacancyLifecycleEvent.objects.filter(
            vacancy=vacancy,
            event_type=VacancyLifecycleEvent.EventType.REAPPEARED,
        ).exists()

    def test_repost_new_id_outside_90_days_creates_new_vacancy(self) -> None:
        _, effective_count = self._run_repost_case(gap_days=120, requisition=None)
        assert effective_count == 2
        assert VacancyEpisode.objects.filter(episode_number=1).count() == 2

    def test_same_requisition_outside_90_days_creates_episode_two(self) -> None:
        vacancy, effective_count = self._run_repost_case(gap_days=120, requisition="REQ-STABLE")
        assert effective_count == 1
        assert VacancyEpisode.objects.filter(
            vacancy=vacancy, episode_number=2, reappearance_gap_days=120
        ).exists()

    def test_official_source_upgrades_canonical_evidence(self) -> None:
        aggregator = self.source("SRC-UPGRADE-AGG", "GENERAL_AGGREGATOR")
        official = self.source("SRC-UPGRADE-OFFICIAL")
        day1 = datetime(2026, 6, 1, tzinfo=UTC)
        self.collect(aggregator, Adapter("A", requisition="REQ-UPGRADE"), day1)
        run_deduplication(day1)
        original = Vacancy.objects.get(merged_into__isnull=True)
        assert original.canonical_posting is not None
        assert original.canonical_posting.source == aggregator

        self.collect(
            official,
            Adapter("B", requisition="REQ-UPGRADE"),
            day1 + timedelta(days=1),
        )
        run_deduplication(day1 + timedelta(days=1))
        original.refresh_from_db()
        assert original.merged_into is None
        assert original.canonical_posting is not None
        assert original.canonical_posting.source == official
        assert Posting.objects.filter(source=aggregator, source_posting_id="A").exists()
        assert VacancyMembershipEvent.objects.filter(
            to_vacancy=original,
            event_type=VacancyMembershipEvent.EventType.CANONICAL_PROMOTE,
        ).exists()

    def test_stale_aggregator_does_not_keep_canonical_vacancy_open(self) -> None:
        aggregator = self.source("SRC-STALE-AGG", "GENERAL_AGGREGATOR")
        official = self.source("SRC-STALE-OFFICIAL")
        opened = datetime(2026, 7, 1, tzinfo=UTC)
        self.collect(aggregator, Adapter("A", requisition="REQ-CLOSE"), opened)
        self.collect(official, Adapter("B", requisition="REQ-CLOSE"), opened)
        run_deduplication(opened)
        vacancy = Vacancy.objects.get(merged_into__isnull=True)
        assert vacancy.canonical_posting is not None
        assert vacancy.canonical_posting.source == official

        closed_at = self.close_posting(official, opened)
        run_deduplication(closed_at)
        vacancy.refresh_from_db()
        assert Posting.objects.get(source=aggregator, source_posting_id="A").current_status in {
            Posting.LifecycleStatus.NEW,
            Posting.LifecycleStatus.STILL_ACTIVE,
        }
        assert vacancy.current_status == Vacancy.Status.CLOSED_OBSERVED

    @staticmethod
    def operational_payload() -> dict[str, list[tuple[object, ...]]]:
        return {
            "vacancies": list(
                Vacancy.objects.order_by("pk").values_list(
                    "pk",
                    "merged_into_id",
                    "canonical_posting_id",
                    "current_status",
                    "first_seen_at",
                    "last_seen_at",
                    "closed_observed_at",
                    "current_episode_number",
                )
            ),
            "memberships": list(
                VacancyPostingMembership.objects.order_by("pk").values_list(
                    "pk",
                    "posting_id",
                    "vacancy_id",
                    "canonical_evidence_role",
                    "link_method",
                )
            ),
            "episodes": list(
                VacancyEpisode.objects.order_by("pk").values_list(
                    "pk",
                    "vacancy_id",
                    "episode_number",
                    "status",
                    "opened_observed_at",
                    "last_seen_at",
                    "closed_observed_at",
                    "positions_count",
                    "multi_hire_possible",
                )
            ),
        }

    def _assert_historical_review_preserves_current(self, *, merge: bool) -> None:
        suffix = "MERGE" if merge else "KEEP"
        source = self.source(f"SRC-HISTORICAL-REVIEW-{suffix}")
        t1 = datetime(2026, 8, 1, tzinfo=UTC)
        t2 = t1 + timedelta(days=1)
        self.collect(source, Adapter("A"), t1)
        self.collect(source, Adapter("B"), t1)
        self.collect(source, Adapter("A", requisition="REQ-HISTORICAL"), t2)
        self.collect(source, Adapter("B", requisition="REQ-HISTORICAL"), t2)

        later_run, _ = run_deduplication(t2)
        current_at_t2 = self.operational_payload()
        earlier_run, _ = run_deduplication(t1)
        review = DedupReviewItem.objects.get(algorithm_decision__dedup_run=earlier_run)

        assert run_summary(later_run)["effective_vacancies"] == 1
        assert run_summary(earlier_run)["effective_vacancies"] == 2
        assert review.run_vacancy_state_a.pk != review.run_vacancy_state_b.pk
        assert self.operational_payload() == current_at_t2
        watermark = VacancyProjectionState.objects.get(identity_version="dedup-v0.1")
        assert watermark.applied_dedup_run == later_run

        resolve_review(
            str(review.pk),
            merge=merge,
            reason="Historical evidence-context resolution",
        )
        review.refresh_from_db()
        assert review.status == (
            DedupReviewItem.Status.MERGED if merge else DedupReviewItem.Status.KEPT_SEPARATE
        )
        assert self.operational_payload() == current_at_t2
        assert run_summary(later_run)["effective_vacancies"] == 1
        assert run_summary(earlier_run)["effective_vacancies"] == 2

    def test_historical_keep_separate_does_not_rewrite_newer_projection(self) -> None:
        self._assert_historical_review_preserves_current(merge=False)

    def test_historical_merge_does_not_rewrite_newer_projection(self) -> None:
        self._assert_historical_review_preserves_current(merge=True)

    def test_reverse_time_run_does_not_move_projection_watermark(self) -> None:
        source = self.source("SRC-PROJECTION-WATERMARK")
        t1 = datetime(2026, 8, 3, tzinfo=UTC)
        t2 = t1 + timedelta(days=1)
        self.collect(source, Adapter("A"), t1)
        self.collect(source, Adapter("B"), t1)
        self.collect(source, Adapter("A", requisition="REQ-WATERMARK"), t2)
        self.collect(source, Adapter("B", requisition="REQ-WATERMARK"), t2)

        later_run, _ = run_deduplication(t2)
        current_at_t2 = self.operational_payload()
        earlier_run, _ = run_deduplication(t1)

        assert run_summary(later_run)["effective_vacancies"] == 1
        assert run_summary(earlier_run)["effective_vacancies"] == 2
        assert self.operational_payload() == current_at_t2
        watermark = VacancyProjectionState.objects.get(identity_version="dedup-v0.1")
        assert watermark.applied_dedup_run == later_run
        assert watermark.applied_as_of == t2

    def test_pending_absence_preserves_material_human_decision(self) -> None:
        source = self.source("SRC-HUMAN-LIFECYCLE-CHANGE")
        when = datetime(2026, 8, 5, tzinfo=UTC)
        self.collect(source, Adapter("A"), when)
        self.collect(source, Adapter("B"), when)
        first_run, _ = run_deduplication(when)
        review = DedupReviewItem.objects.get(algorithm_decision__dedup_run=first_run)
        human = resolve_review(str(review.pk), merge=False, reason="Initial PIT evidence")
        first_fingerprint = human.evidence["pair_evidence_fingerprint"]

        later = when + timedelta(days=1)
        self.collect_empty(source, later)
        later_run, _ = run_deduplication(human.created_at + timedelta(seconds=1))
        assert not DedupReviewItem.objects.filter(algorithm_decision__dedup_run=later_run).exists()
        inherited = DedupDecision.objects.filter(
            dedup_run=later_run,
            evidence__material_version="dedup-review-material-v0.1",
        ).get()
        assert inherited.evidence["pair_evidence_fingerprint"] != first_fingerprint
        assert inherited.inherited_review_application.source_human_decision == human

    def _legacy_human(self, algorithm: DedupDecision, *, outcome: str) -> DedupDecision:
        return DedupDecision.objects.create(
            dedup_run=algorithm.dedup_run,
            posting_a=algorithm.posting_a,
            posting_b=algorithm.posting_b,
            observation_a=algorithm.observation_a,
            observation_b=algorithm.observation_b,
            dedup_version=algorithm.dedup_version,
            normalizer_version=algorithm.normalizer_version,
            method=DedupDecision.Method.HUMAN,
            outcome=outcome,
            score=algorithm.score,
            feature_scores=algorithm.feature_scores,
            weights=algorithm.weights,
            blocking_evidence=algorithm.blocking_evidence,
            hard_barriers=algorithm.hard_barriers,
            evidence={"algorithm_decision_id": str(algorithm.pk), "reason": "legacy fixture"},
        )

    def test_legacy_material_reconstruction_and_direct_authority_xor(self) -> None:
        source = self.source("SRC-LEGACY-BRIDGE")
        when = datetime(2026, 8, 6, tzinfo=UTC)
        self.collect(source, Adapter("A"), when)
        self.collect(source, Adapter("B"), when)
        first_run, _ = run_deduplication(when)
        algorithm = DedupReviewItem.objects.get(
            algorithm_decision__dedup_run=first_run
        ).algorithm_decision
        human = self._legacy_human(algorithm, outcome=DedupDecision.Outcome.KEEP_SEPARATE)
        proof = reconstruct_source_human_material(human, FROZEN_CONFIGURATION)
        assert proof.algorithm_decision == algorithm

        later_run, _ = run_deduplication(human.created_at + timedelta(seconds=1))
        target_review = DedupReviewItem.objects.get(algorithm_decision__dedup_run=later_run)
        application, created = create_dedup_review_application(
            target_algorithm_decision=target_review.algorithm_decision,
            source_human_decision=human,
            configuration=FROZEN_CONFIGURATION,
        )
        assert created
        assert application.material_fingerprint == proof.material_fingerprint
        for merge in (False, True):
            with self.assertRaisesRegex(ValueError, "inherited authority"):
                resolve_review(str(target_review.pk), merge=merge, reason="must fail closed")

    def test_legacy_bridge_rejects_changed_or_unverifiable_source(self) -> None:
        source = self.source("SRC-LEGACY-INVALID")
        when = datetime(2026, 8, 7, tzinfo=UTC)
        self.collect(source, Adapter("A"), when)
        self.collect(source, Adapter("B"), when)
        first_run, _ = run_deduplication(when)
        algorithm = DedupReviewItem.objects.get(
            algorithm_decision__dedup_run=first_run
        ).algorithm_decision
        human = self._legacy_human(algorithm, outcome=DedupDecision.Outcome.KEEP_SEPARATE)
        human.evidence = {"reason": "missing source algorithm"}
        with self.assertRaises(UnverifiableLegacyHumanDecisionError):
            reconstruct_source_human_material(human, FROZEN_CONFIGURATION)

        human.evidence = {
            "algorithm_decision_id": str(algorithm.pk),
            "material_fingerprint": "0" * 64,
        }
        with self.assertRaisesRegex(DedupContinuityValidationError, "stored source material"):
            reconstruct_source_human_material(human, FROZEN_CONFIGURATION)

    def test_dedup_application_model_rejects_forged_authority(self) -> None:
        source = self.source("SRC-FORGED-APP")
        when = datetime(2026, 8, 8, tzinfo=UTC)
        self.collect(source, Adapter("A"), when)
        self.collect(source, Adapter("B"), when)
        run, _ = run_deduplication(when)
        algorithm = DedupReviewItem.objects.get(
            algorithm_decision__dedup_run=run
        ).algorithm_decision
        human = self._legacy_human(algorithm, outcome=DedupDecision.Outcome.KEEP_SEPARATE)
        forged = DedupReviewDecisionApplication(
            target_algorithm_decision=algorithm,
            source_human_decision=human,
            material_fingerprint="0" * 64,
            fingerprint_version="wrong-version",
            evidence={"source_decision_id": "wrong", "target_decision_id": "wrong"},
        )
        with self.assertRaises(Exception):
            forged.save()
