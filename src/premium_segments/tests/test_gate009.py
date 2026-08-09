from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.test import RequestFactory, TestCase

from core.models import RawArtifact
from observations.models import CollectionRun, GreenRelevanceAssessment, Posting, PostingObservation
from premium_segments.admin import ReadOnlyPremiumAdmin
from premium_segments.classifier import (
    EmployerEvidenceInput,
    PremiumSegmentClassifier,
    run_classification,
)
from premium_segments.models import (
    EmployerProfileEvidence,
    ImmutablePremiumEvidenceError,
    PremiumSegmentAssessment,
    PremiumSegmentReviewItem,
    PremiumSegmentRun,
)
from reference_data.models import PremiumSignal
from sources.models import Source

GREEN = "GREEN_CONFIRMED"


class PremiumClassifierRulesTests(TestCase):
    classifier = PremiumSegmentClassifier()

    def classify(self, text: str = "", **kwargs: Any):
        return self.classifier.classify(description=text, green_result=GREEN, **kwargs)

    def test_enea_explicit_job_signal_p003(self) -> None:
        decision = self.classify("Wir betreuen exklusive Kundschaft.")
        assert decision.segment == "PRIVATE_RESIDENTIAL_PREMIUM"
        assert decision.method == "EXPLICIT_JOB_SIGNAL"
        assert {match["signal_id"] for match in decision.matches} == {"P003"}
        assert decision.evidence_strength == "STRONG"

    def test_randstad_job_text_not_agency_identity_is_premium(self) -> None:
        decision = self.classify("Pflege hochwertige Privatgärten")
        assert decision.segment == "PRIVATE_RESIDENTIAL_PREMIUM"
        assert "P001" in {match["signal_id"] for match in decision.matches}
        assert all(match["matched_field"] != "SOURCE_NAME" for match in decision.matches)

    def test_nfkc_case_punctuation_and_whitespace(self) -> None:
        decision = self.classify("HOCHWERTIGE---PRIVATGÄRTEN   und Pflege")
        assert decision.segment == "PRIVATE_RESIDENTIAL_PREMIUM"
        assert "P001" in {match["signal_id"] for match in decision.matches}

    def test_job_only_scope_does_not_match_employer_profile(self) -> None:
        decision = self.classifier.classify(
            green_result=GREEN,
            employer_evidence=(EmployerEvidenceInput("profile", "exklusive Kundschaft"),),
        )
        assert decision.segment == "UNKNOWN"
        assert not decision.matches

    def test_weak_private_and_auxiliary_semantics(self) -> None:
        private = self.classify("Pflege eines Privatgartens")
        assert private.segment == "PRIVATE_RESIDENTIAL_STANDARD"
        assert private.status == "CLASSIFIED"
        for text in ("Gartendesign Pool Naturstein", "Diskretion und live-in"):
            auxiliary = self.classify(text)
            assert auxiliary.segment == "UNKNOWN"
            assert auxiliary.status == "NO_SUFFICIENT_EVIDENCE"

    def test_estate_role_requires_green_admission(self) -> None:
        decision = self.classifier.classify(title="Estate Manager", green_result="REVIEW")
        assert decision.status == "SKIPPED_NOT_GREEN"
        assert decision.segment == "UNKNOWN"

    def test_prohibited_wealth_inference_is_never_positive(self) -> None:
        decision = self.classifier.classify(
            green_result=GREEN,
            inference_evidence="municipio rico y precio inmobiliario local",
        )
        assert decision.segment == "UNKNOWN"
        assert decision.status == "NO_SUFFICIENT_EVIDENCE"
        assert {item["signal_id"] for item in decision.prohibited} == {"N001", "N002"}
        assert decision.reason_codes == ("PROHIBITED_INFERENCE_ONLY",)

    def test_conflicting_explicit_segments_enter_review(self) -> None:
        decision = self.classify("exklusive Kundschaft auf einer private villa")
        assert decision.segment == "UNKNOWN"
        assert decision.status == "REVIEW"


class PremiumSegmentPersistenceTests(TestCase):
    sequence = 0

    def source(
        self, source_id: str, name: str | None = None, source_type: str = "DIRECT_PUBLIC_EMPLOYER"
    ) -> Source:
        return Source.objects.create(
            source_id=source_id,
            source_name=name or source_id,
            domain=f"{source_id.casefold()}.test",
            source_family="TEST",
            source_type=source_type,
            priority="P0",
            coverage_scope="fixture",
            canonicality="CANONICAL",
            platform_family="FIXTURE",
            access_method="FIXTURE",
            automation_status="COLLECTOR_CANDIDATE",
            legal_review_status="APPROVED",
            verification_status="VERIFIED",
            official_url=f"https://{source_id.casefold()}.test/",
        )

    def observation(
        self,
        source: Source,
        posting_id: str,
        when: datetime,
        *,
        title: str = "Gärtner",
        employer: str = "Fixture Employer",
        text: str = "Gartenunterhalt",
        green: str = GREEN,
        street: str = "",
        locality: str = "Winterthur",
    ) -> PostingObservation:
        self.sequence += 1
        listing = f"https://{source.domain}/jobs"
        run = CollectionRun.objects.create(
            source=source,
            started_at=when,
            finished_at=when,
            status=CollectionRun.Status.SUCCEEDED,
            run_scope=CollectionRun.RunScope.TARGETED,
            source_health_status=CollectionRun.SourceHealthStatus.HEALTHY,
            listing_url=listing,
        )
        posting, created = Posting.objects.get_or_create(
            source=source,
            source_posting_id=posting_id,
            defaults={
                "first_seen_at": when,
                "last_seen_at": when,
                "latest_canonical_url": f"https://{source.domain}/jobs/{posting_id}",
            },
        )
        if not created:
            posting.last_seen_at = when
            posting.save(update_fields=["last_seen_at", "updated_at"])
        body = f"fixture-{self.sequence}".encode()
        digest = hashlib.sha256(body).hexdigest()
        raw = RawArtifact.objects.create(
            object_key=f"premium-fixture/{self.sequence}.html",
            sha256_digest=digest,
            byte_size=len(body),
            content_type="text/html",
        )
        observation = PostingObservation.objects.create(
            collection_run=run,
            posting=posting,
            source=source,
            observation_status="ACTIVE",
            source_posting_id=posting_id,
            observed_at=when,
            canonical_url=f"https://{source.domain}/jobs/{posting_id}",
            title=title,
            hiring_organization=employer,
            description_html=text,
            location_street=street,
            location_locality=locality,
            location_country="CH",
            raw_artifact=raw,
            structured_payload={"description": text},
            contract_payload={
                "schema_version": "1.2",
                "observation_status": "ACTIVE",
                "raw_payload_sha256": digest,
            },
        )
        GreenRelevanceAssessment.objects.create(
            posting_observation=observation,
            classifier_version="green-relevance-v0.1",
            taxonomy_version="research-v0.4",
            taxonomy_sha256="b" * 64,
            result=green,
            evidence={"fixture": True},
            created_at=when,
        )
        return observation

    def profile(self, employer: str, text: str, available_at: datetime) -> EmployerProfileEvidence:
        return EmployerProfileEvidence.objects.create(
            employer_name=employer,
            evidence_text=text,
            evidence_type="PREMIUM_PROFILE",
            source_url="https://fixture.test/profile",
            available_at=available_at,
            raw_sha256=hashlib.sha256(text.encode()).hexdigest(),
            evidence_version="employer-profile-v0.1",
            provenance={"fixture": "GATE-009"},
            created_at=available_at,
        )

    def assessment(
        self, run: PremiumSegmentRun, observation: PostingObservation
    ) -> PremiumSegmentAssessment:
        return PremiumSegmentAssessment.objects.get(run=run, posting_observation=observation)

    def test_glowing_grass_requires_pit_profile_evidence(self) -> None:
        source = self.source("SRC-GLOWING")
        t1 = datetime(2026, 8, 1, tzinfo=UTC)
        observation = self.observation(source, "GG-1", t1, employer="Glowing Grass")
        profile = self.profile("Glowing Grass", "Arbeit im Premiumsegment", t1 + timedelta(days=1))

        later_run, _ = run_classification(t1 + timedelta(days=1))
        later = self.assessment(later_run, observation)
        earlier_run, _ = run_classification(t1)
        earlier = self.assessment(earlier_run, observation)

        assert later.segment == "PRIVATE_RESIDENTIAL_PREMIUM"
        assert later.method == "EMPLOYER_PROFILE_SIGNAL"
        assert later.employer_profile_evidence == profile
        assert earlier.segment == "UNKNOWN"
        assert earlier.employer_profile_evidence is None
        earlier_snapshot = (earlier.segment, earlier.assessment_status, earlier.evidence)
        later_run.refresh_from_db()
        earlier.refresh_from_db()
        assert (earlier.segment, earlier.assessment_status, earlier.evidence) == earlier_snapshot

    def test_private_villa_privacy_and_command_output(self) -> None:
        source = self.source("SRC-VILLA")
        when = datetime(2026, 8, 2, tzinfo=UTC)
        street = "Confidentialstrasse 12"
        observation = self.observation(
            source, "V-1", when, text="Gartenpflege auf einer private villa", street=street
        )
        run, _ = run_classification(when)
        assessment = self.assessment(run, observation)
        output = StringIO()
        call_command("classify_premium_segments", "--as-of", when.isoformat(), stdout=output)

        assert assessment.segment == "PRIVATE_ESTATE_DIRECT"
        assert assessment.privacy_context == "PRIVATE_RESIDENCE"
        assert "P006" in assessment.matched_signal_ids
        assert street not in json.dumps(assessment.evidence)
        assert street not in json.dumps(assessment.matched_evidence)
        assert street not in output.getvalue()

    def test_homeservice_source_name_is_not_evidence_but_privatgarten_is_standard(self) -> None:
        source = self.source("SRC-HOME24", "Homeservice24", "PRIVATE_HOUSEHOLD_DIRECT")
        when = datetime(2026, 8, 3, tzinfo=UTC)
        generic = self.observation(source, "H-1", when, employer="Private household")
        explicit = self.observation(
            source, "H-2", when, employer="Private household", text="Pflege Privatgarten"
        )
        run, _ = run_classification(when)
        assert self.assessment(run, generic).segment == "UNKNOWN"
        assert self.assessment(run, explicit).segment == "PRIVATE_RESIDENTIAL_STANDARD"

    def test_public_job_wealthy_locality_and_ett_name_are_not_evidence(self) -> None:
        city = self.source("SRC-WEALTHY", "Wealthy City")
        agency = self.source("SRC-ETT", "Randstad", "STAFFING_AGENCY")
        when = datetime(2026, 8, 4, tzinfo=UTC)
        city_obs = self.observation(city, "C-1", when, locality="Küsnacht")
        agency_obs = self.observation(agency, "A-1", when, employer="Randstad")
        run, _ = run_classification(when)
        assert self.assessment(run, city_obs).segment == "UNKNOWN"
        assert self.assessment(run, agency_obs).segment == "UNKNOWN"

    def test_traceability_review_and_append_only_guards(self) -> None:
        source = self.source("SRC-TRACE")
        when = datetime(2026, 8, 5, tzinfo=UTC)
        observation = self.observation(
            source, "T-1", when, text="exklusive Kundschaft private estate"
        )
        run, _ = run_classification(when)
        assessment = self.assessment(run, observation)
        review = PremiumSegmentReviewItem.objects.get(assessment=assessment)

        assert assessment.assessment_status == "REVIEW"
        assert {item["field"] for item in assessment.matched_fields_and_scopes} == {"DESCRIPTION"}
        assert review.status == "PENDING"
        assessment.segment = "PRIVATE_ESTATE_DIRECT"
        with pytest.raises(ImmutablePremiumEvidenceError):
            assessment.save()
        with pytest.raises(ImmutablePremiumEvidenceError):
            PremiumSegmentAssessment.objects.filter(pk=assessment.pk).update(segment="UNKNOWN")
        with pytest.raises(ImmutablePremiumEvidenceError):
            PremiumSegmentAssessment.objects.filter(pk=assessment.pk).delete()
        with pytest.raises(ImmutablePremiumEvidenceError):
            PremiumSegmentAssessment.objects.bulk_update([assessment], ["segment"])

    def test_admin_is_observational(self) -> None:
        model_admin = ReadOnlyPremiumAdmin(PremiumSegmentAssessment, AdminSite())
        request = RequestFactory().get("/admin/")
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request) is False
        assert model_admin.has_delete_permission(request) is False
        assert set(model_admin.get_readonly_fields(request)) == {
            field.name for field in PremiumSegmentAssessment._meta.fields
        }

    def test_exact_replay_changed_observation_and_version_coexistence(self) -> None:
        source = self.source("SRC-VERSION")
        t1 = datetime(2026, 8, 6, tzinfo=UTC)
        first = self.observation(source, "P-1", t1)
        first_run, reused = run_classification(t1)
        same_run, reused_again = run_classification(t1)
        assert reused is False and reused_again is True and same_run.pk == first_run.pk

        t2 = t1 + timedelta(days=1)
        second = self.observation(source, "P-1", t2, text="hochwertige Privatgärten")
        second_run, _ = run_classification(t2)
        future_version, _ = run_classification(t2, classifier_version="premium-segment-v0.2")
        assert first_run.input_fingerprint != second_run.input_fingerprint
        assert future_version.pk != second_run.pk
        assert self.assessment(first_run, first).segment == "UNKNOWN"
        assert self.assessment(second_run, second).segment == "PRIVATE_RESIDENTIAL_PREMIUM"
        assert PremiumSegmentAssessment.objects.filter(posting_observation=second).count() == 2

    def test_frozen_reference_signals_are_not_mutated(self) -> None:
        signal = PremiumSignal.objects.create(
            signal_id="PX01",
            signal_group="TEST",
            search_term="immutable",
            evidence_scope="JOB",
            base_weight="0.1000",
            default_segment="UNKNOWN",
            notes="fixture",
        )
        before = tuple(
            PremiumSignal.objects.filter(pk=signal.pk)
            .values_list("signal_group", "search_term", "base_weight", "default_segment", "notes")
            .get()
        )
        PremiumSegmentClassifier().classify(description="exklusive Kundschaft", green_result=GREEN)
        after = tuple(
            PremiumSignal.objects.filter(pk=signal.pk)
            .values_list("signal_group", "search_term", "base_weight", "default_segment", "notes")
            .get()
        )
        assert after == before
