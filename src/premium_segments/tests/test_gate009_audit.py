from __future__ import annotations

import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase

from core.models import RawArtifact
from observations.models import (
    CollectionRun,
    GreenRelevanceAssessment,
    Posting,
    PostingLifecycleEvent,
    PostingObservation,
)
from premium_segments.classifier import (
    EmployerEvidenceInput,
    PremiumSegmentClassifier,
    PremiumSegmentError,
    run_classification,
)
from premium_segments.models import (
    EmployerProfileEvidence,
    PremiumSegmentAssessment,
    PremiumSegmentAssessmentEmployerEvidence,
    PremiumSegmentReviewItem,
    PremiumSegmentRun,
)
from sources.models import Source

GREEN = "GREEN_CONFIRMED"


def make_source(source_id: str) -> Source:
    slug = source_id.casefold().replace("_", "-")
    return Source.objects.create(
        source_id=source_id,
        source_name=source_id,
        domain=f"{slug}.test",
        source_family="TEST",
        source_type="DIRECT_PRIVATE_EMPLOYER",
        priority="P0",
        coverage_scope="fixture",
        canonicality="CANONICAL",
        platform_family="FIXTURE",
        access_method="FIXTURE",
        automation_status="COLLECTOR_CANDIDATE",
        legal_review_status="APPROVED",
        verification_status="VERIFIED",
        official_url=f"https://{slug}.test/",
    )


def make_observation(
    source: Source,
    posting_id: str,
    when: datetime,
    *,
    title: str = "Gärtner",
    employer: str = "Fixture Employer",
    description: str = "Gartenunterhalt",
    identity_key: str = "",
    status: str = "ACTIVE",
    lifecycle: str | None = None,
    green_result: str | None = GREEN,
    green_version: str = "green-relevance-v0.1",
    green_created_at: datetime | None = None,
    contract_overrides: dict[str, object] | None = None,
) -> PostingObservation:
    canonical_url = f"https://{source.domain}/jobs/{posting_id}"
    run = CollectionRun.objects.create(
        source=source,
        started_at=when,
        finished_at=when,
        status=CollectionRun.Status.SUCCEEDED,
        run_scope=CollectionRun.RunScope.TARGETED,
        source_health_status=CollectionRun.SourceHealthStatus.HEALTHY,
        listing_url=f"https://{source.domain}/jobs",
    )
    posting, _ = Posting.objects.get_or_create(
        source=source,
        source_posting_id=posting_id,
        defaults={
            "first_seen_at": when,
            "last_seen_at": when,
            "latest_canonical_url": canonical_url,
        },
    )
    body = f"{source.pk}:{posting_id}:{when.isoformat()}:{status}".encode()
    digest = hashlib.sha256(body).hexdigest()
    raw = RawArtifact.objects.create(
        object_key=f"premium-audit/{uuid.uuid4()}.html",
        sha256_digest=digest,
        byte_size=len(body),
        content_type="text/html",
    )
    contract: dict[str, object] = {
        "schema_version": "1.2",
        "source_id": str(source.pk),
        "source_native_id": posting_id,
        "observed_at": when.isoformat(),
        "observation_status": status,
        "source_url": canonical_url,
        "canonical_url": canonical_url,
        "http_status": 200,
        "raw_title": title,
        "raw_location": "Winterthur",
        "raw_employer": employer,
        "raw_text": description,
        "raw_payload_sha256": digest,
        "published_at_raw": None,
        "source_published_at": None,
        "source_updated_at": None,
        "published_at_precision": "UNKNOWN",
        "published_at_parse_method": "MISSING",
        "published_at_confidence": None,
        "collector_run_id": str(run.pk),
        "source_health_status": "HEALTHY",
        "normalized_location": None,
    }
    contract.update(contract_overrides or {})
    observation = PostingObservation.objects.create(
        collection_run=run,
        posting=posting,
        source=source,
        observation_status=status,
        source_posting_id=posting_id,
        observed_at=when,
        canonical_url=canonical_url,
        title=title,
        hiring_organization=employer,
        description_html=description,
        location_locality="Winterthur",
        location_country="CH",
        raw_artifact=raw,
        structured_payload={
            "description": description,
            "employer_identity_key": identity_key,
        },
        contract_payload=contract,
    )
    if green_result is not None:
        GreenRelevanceAssessment.objects.create(
            posting_observation=observation,
            classifier_version=green_version,
            taxonomy_version="research-v0.4",
            taxonomy_sha256="b" * 64,
            result=green_result,
            evidence={"audit": True},
            created_at=green_created_at or when,
        )
    if lifecycle is not None:
        PostingLifecycleEvent.objects.create(
            posting=posting,
            posting_observation=observation,
            collection_run=run,
            event_type=lifecycle,
            observed_at=when,
            source_health_status="HEALTHY",
            evidence={"audit": True},
        )
    return observation


def make_profile(
    source: Source,
    identity_key: str,
    employer: str,
    text: str,
    available_at: datetime,
    *,
    version: str = "employer-profile-v0.1",
) -> EmployerProfileEvidence:
    return EmployerProfileEvidence.objects.create(
        source=source,
        employer_identity_key=identity_key,
        employer_name=employer,
        evidence_text=text,
        evidence_type="PREMIUM_PROFILE",
        source_url=f"https://{source.domain}/profile",
        available_at=available_at,
        raw_sha256=hashlib.sha256(text.encode()).hexdigest(),
        evidence_version=version,
        provenance={"fixture": "GATE-009-AUDIT", "identity_basis": identity_key},
        created_at=available_at,
    )


def empty_run(when: datetime) -> PremiumSegmentRun:
    return PremiumSegmentRun.objects.create(
        as_of=when,
        classifier_version="premium-segment-v0.1",
        normalizer_version="premium-normalizer-v0.1",
        taxonomy_version="research-v0.4",
        taxonomy_sha256="a" * 64,
        configuration={"audit": True},
        input_fingerprint=hashlib.sha256(when.isoformat().encode()).hexdigest(),
        status="SUCCEEDED",
        started_at=when,
        finished_at=when,
    )


class PremiumMatchingAndScopeAuditTests(TestCase):
    classifier = PremiumSegmentClassifier()

    def classify(self, text: str = "", **kwargs: Any):
        return self.classifier.classify(description=text, green_result=GREEN, **kwargs)

    def test_short_estate_abbreviations_require_token_boundaries(self) -> None:
        for ordinary in ("Wohnwelt", "Wohnwagen", "Wohnanlage", "Wohnwerk", "Kuhnweg"):
            assert self.classify(ordinary).segment == "UNKNOWN"
        assert self.classify("Kundschaft: HNW.").segment == "PRIVATE_ESTATE_DIRECT"
        assert self.classify("UHNW-Kundschaft").segment == "PRIVATE_ESTATE_DIRECT"
        assert self.classify("UHNWI").segment == "UNKNOWN"
        assert self.classify("high-net-worth").segment == "UNKNOWN"

    def test_phrase_boundaries_and_punctuation_are_deterministic(self) -> None:
        expected = {
            "hochwertige Privatgärten": "P001",
            "HOCHWERTIGE---PRIVATGÄRTEN": "P001",
            "exklusive Kundschaft": "P003",
            "private villa": "P006",
            "private estate": "P007",
            "family office": "P011",
            "Privatgarten": "P024",
        }
        for text, signal_id in expected.items():
            decision = self.classify(text)
            assert signal_id in {match["signal_id"] for match in decision.matches}

    def test_markup_attributes_scripts_and_urls_are_not_job_evidence(self) -> None:
        hidden = (
            '<div class="private villa" data-note="exklusive Kundschaft">Arbeit</div>'
            "<script>hochwertige Privatgärten</script>"
            " https://example.test/private-estate/family-office"
        )
        assert self.classify(hidden).segment == "UNKNOWN"
        visible = self.classify("<p>Arbeit für <strong>exklusive Kundschaft</strong></p>")
        assert visible.segment == "PRIVATE_RESIDENTIAL_PREMIUM"

    def test_scope_matrix_is_explicit_and_fail_closed_for_source_profiles(self) -> None:
        profile_p003 = (EmployerEvidenceInput("p3", "exklusive Kundschaft"),)
        assert (
            self.classifier.classify(green_result=GREEN, employer_evidence=profile_p003).matches
            == ()
        )
        profile_p001 = (EmployerEvidenceInput("p1", "hochwertige Privatgärten"),)
        assert (
            self.classifier.classify(green_result=GREEN, employer_evidence=profile_p001).segment
            == "PRIVATE_RESIDENTIAL_PREMIUM"
        )
        profile_p009 = (EmployerEvidenceInput("p9", "HNW"),)
        assert (
            self.classifier.classify(green_result=GREEN, employer_evidence=profile_p009).matches
            == ()
        )
        assert self.classifier.classify(title="Estate Manager", green_result=GREEN).segment == (
            "PRIVATE_ESTATE_DIRECT"
        )
        prohibited = self.classifier.classify(
            description="municipio rico",
            inference_evidence="municipio rico",
            green_result=GREEN,
        )
        assert prohibited.segment == "UNKNOWN"
        assert not prohibited.matches
        assert {item["signal_id"] for item in prohibited.prohibited} == {"N001"}

    def test_decision_combination_precedence_and_privacy(self) -> None:
        cases = [
            ("exklusive Kundschaft Privatgarten", "PRIVATE_RESIDENTIAL_PREMIUM", "CLASSIFIED"),
            ("private estate Privatgarten", "PRIVATE_ESTATE_DIRECT", "CLASSIFIED"),
            ("Head Gardener private estate", "PRIVATE_ESTATE_DIRECT", "CLASSIFIED"),
            ("anspruchsvolle Kundengärten Gartendesign", "UNKNOWN", "REVIEW"),
            ("Privatgarten Pool", "PRIVATE_RESIDENTIAL_STANDARD", "CLASSIFIED"),
            ("exklusive Kundschaft private estate", "UNKNOWN", "REVIEW"),
        ]
        for text, segment, status in cases:
            decision = self.classify(text)
            assert (decision.segment, decision.status) == (segment, status)
        premium = self.classify("exklusive Kundschaft")
        assert premium.privacy_context == "PRIVATE_RESIDENCE"


class PremiumPITAndIdentityAuditTests(TestCase):
    def test_employer_profile_requires_explicit_source_and_identity_binding(self) -> None:
        source_a = make_source("SRC-IDENTITY-A")
        source_b = make_source("SRC-IDENTITY-B")
        when = datetime(2026, 9, 1, tzinfo=UTC)
        identity = "employer:shared-label:a"
        observation = make_observation(
            source_a,
            "A-1",
            when,
            employer="  Shared   Employer AG ",
            identity_key=identity,
        )
        make_profile(
            source_b,
            identity,
            "Shared Employer AG",
            "Premiumsegment",
            when,
        )
        first_run, _ = run_classification(when)
        first = PremiumSegmentAssessment.objects.get(run=first_run, posting_observation=observation)
        assert first.segment == "UNKNOWN"
        make_profile(
            source_a,
            identity,
            "Shared Employer AG",
            "Premiumsegment",
            when,
        )
        second_run, _ = run_classification(when)
        second = PremiumSegmentAssessment.objects.get(
            run=second_run, posting_observation=observation
        )
        assert second.segment == "PRIVATE_RESIDENTIAL_PREMIUM"
        assert first_run.input_fingerprint != second_run.input_fingerprint

    def test_profiles_are_cumulative_assertions_and_all_are_fingerprinted_and_linked(self) -> None:
        source = make_source("SRC-CUMULATIVE")
        when = datetime(2026, 9, 2, tzinfo=UTC)
        identity = "source:SRC-CUMULATIVE"
        observation = make_observation(
            source,
            "C-1",
            when,
            employer="Cumulative Employer",
            identity_key=identity,
        )
        first_profile = make_profile(
            source,
            identity,
            "Cumulative Employer",
            "Premiumsegment",
            when,
            version="assertion-v1",
        )
        second_profile = make_profile(
            source,
            identity,
            "Cumulative Employer",
            "Unrelated current profile text",
            when + timedelta(minutes=1),
            version="assertion-v2",
        )
        run, _ = run_classification(when + timedelta(minutes=1))
        assessment = PremiumSegmentAssessment.objects.get(run=run, posting_observation=observation)
        assert assessment.segment == "PRIVATE_RESIDENTIAL_PREMIUM"
        linked = set(
            PremiumSegmentAssessmentEmployerEvidence.objects.filter(
                assessment=assessment
            ).values_list("employer_profile_evidence_id", flat=True)
        )
        assert linked == {first_profile.pk, second_profile.pk}
        assert set(assessment.evidence["employer_profile_evidence_ids"]) == {
            str(first_profile.pk),
            str(second_profile.pk),
        }

    def test_profile_legal_suffix_mismatch_fails_closed(self) -> None:
        source = make_source("SRC-SUFFIX")
        when = datetime(2026, 9, 3, tzinfo=UTC)
        identity = "source:SRC-SUFFIX"
        observation = make_observation(
            source,
            "S-1",
            when,
            employer="Example AG",
            identity_key=identity,
        )
        make_profile(source, identity, "Example GmbH", "Premiumsegment", when)
        run, _ = run_classification(when)
        assert (
            PremiumSegmentAssessment.objects.get(run=run, posting_observation=observation).segment
            == "UNKNOWN"
        )

    def test_green_selection_is_versioned_and_point_in_time(self) -> None:
        source = make_source("SRC-GREEN-PIT")
        t1 = datetime(2026, 9, 4, tzinfo=UTC)
        observation = make_observation(
            source,
            "G-1",
            t1,
            description="exklusive Kundschaft",
            green_result=GREEN,
            green_version="green-relevance-v0.2",
        )
        future_green = GreenRelevanceAssessment.objects.create(
            posting_observation=observation,
            classifier_version="green-relevance-v0.1",
            taxonomy_version="research-v0.4",
            taxonomy_sha256="b" * 64,
            result=GREEN,
            evidence={"future": True},
            created_at=t1 + timedelta(days=1),
        )
        early_run, _ = run_classification(t1)
        early = PremiumSegmentAssessment.objects.get(run=early_run, posting_observation=observation)
        assert early.assessment_status == "SKIPPED_NOT_GREEN"
        assert early.green_relevance_assessment is None
        late_run, _ = run_classification(t1 + timedelta(days=1))
        late = PremiumSegmentAssessment.objects.get(run=late_run, posting_observation=observation)
        assert late.segment == "PRIVATE_RESIDENTIAL_PREMIUM"
        assert late.green_relevance_assessment == future_green
        assert early_run.input_fingerprint != late_run.input_fingerprint

    def test_reverse_order_lifecycle_pit_never_uses_current_posting_state(self) -> None:
        source = make_source("SRC-LIFECYCLE-PIT")
        t1 = datetime(2026, 9, 5, tzinfo=UTC)
        t2, t3, t4 = (t1 + timedelta(days=index) for index in (1, 3, 4))
        first = make_observation(
            source,
            "L-1",
            t1,
            description="exklusive Kundschaft",
            lifecycle="NEW",
        )
        make_observation(
            source,
            "L-1",
            t2,
            status="NOT_FOUND",
            lifecycle="DISAPPEARED_PENDING",
            green_result=None,
        )
        make_observation(
            source,
            "L-1",
            t3,
            status="NOT_FOUND",
            lifecycle="CLOSED_OBSERVED",
            green_result=None,
        )
        reappeared = make_observation(
            source,
            "L-1",
            t4,
            description="exklusive Kundschaft",
            lifecycle="STILL_ACTIVE",
        )
        run_t4, _ = run_classification(t4)
        run_t3, _ = run_classification(t3)
        run_t2, _ = run_classification(t2)
        run_t1, _ = run_classification(t1)
        assert run_t4.observations_considered == 1
        assert run_t3.observations_considered == 0
        assert run_t2.observations_considered == 0
        assert run_t1.observations_considered == 1
        assert PremiumSegmentAssessment.objects.get(run=run_t4).posting_observation == reappeared
        assert PremiumSegmentAssessment.objects.get(run=run_t1).posting_observation == first
        t1_snapshot = tuple(
            PremiumSegmentAssessment.objects.filter(run=run_t1).values_list(
                "posting_observation_id", "segment", "assessment_status"
            )
        )
        run_t4.refresh_from_db()
        assert (
            tuple(
                PremiumSegmentAssessment.objects.filter(run=run_t1).values_list(
                    "posting_observation_id", "segment", "assessment_status"
                )
            )
            == t1_snapshot
        )

    def test_contract_validation_rejects_schema_and_raw_provenance_corruption(self) -> None:
        source = make_source("SRC-CONTRACT")
        when = datetime(2026, 9, 10, tzinfo=UTC)
        make_observation(
            source,
            "BAD-1",
            when,
            contract_overrides={"raw_payload_sha256": "0" * 64},
        )
        with pytest.raises(PremiumSegmentError, match="inconsistent contract provenance"):
            run_classification(when)
        assert PremiumSegmentRun.objects.count() == 0

    def test_contract_validation_rejects_missing_required_fields(self) -> None:
        source = make_source("SRC-CONTRACT-SCHEMA")
        when = datetime(2026, 9, 11, tzinfo=UTC)
        make_observation(
            source,
            "BAD-2",
            when,
            contract_overrides={"source_url": None},
        )
        with pytest.raises(PremiumSegmentError, match="failed frozen contract validation"):
            run_classification(when)
        assert PremiumSegmentRun.objects.count() == 0

    def test_green_status_matrix_uses_real_versioned_rows(self) -> None:
        source = make_source("SRC-GREEN-MATRIX")
        when = datetime(2026, 9, 12, tzinfo=UTC)
        observations = {
            "green": make_observation(source, "GREEN", when, green_result="GREEN_CONFIRMED"),
            "review": make_observation(source, "REVIEW", when, green_result="REVIEW"),
            "not_green": make_observation(source, "NOT", when, green_result="NOT_GREEN"),
            "missing": make_observation(source, "MISSING", when, green_result=None),
        }
        run, _ = run_classification(when)
        statuses = {
            key: PremiumSegmentAssessment.objects.get(
                run=run, posting_observation=observation
            ).assessment_status
            for key, observation in observations.items()
        }
        assert statuses == {
            "green": "NO_SUFFICIENT_EVIDENCE",
            "review": "SKIPPED_NOT_GREEN",
            "not_green": "SKIPPED_NOT_GREEN",
            "missing": "SKIPPED_NOT_GREEN",
        }

    def test_profile_address_is_not_replicated_in_derived_or_command_evidence(self) -> None:
        source = make_source("SRC-PRIVATE-PROFILE")
        when = datetime(2026, 9, 13, tzinfo=UTC)
        identity = "source:SRC-PRIVATE-PROFILE"
        street = "Confidentialstrasse 12"
        observation = make_observation(
            source,
            "P-1",
            when,
            employer="Private Employer",
            identity_key=identity,
        )
        make_profile(
            source,
            identity,
            "Private Employer",
            f"Premiumsegment {street}",
            when,
        )
        run, _ = run_classification(when)
        assessment = PremiumSegmentAssessment.objects.get(run=run, posting_observation=observation)
        serialized = json.dumps(
            {
                "evidence": assessment.evidence,
                "matched": assessment.matched_evidence,
                "fields": assessment.matched_fields_and_scopes,
            }
        )
        output = StringIO()
        call_command("classify_premium_segments", "--as-of", when.isoformat(), stdout=output)
        assert street not in serialized
        assert street not in output.getvalue()
        assert assessment.privacy_context == "PRIVATE_RESIDENCE"

    def test_conflicting_profile_and_job_evidence_enters_review(self) -> None:
        source = make_source("SRC-PROFILE-CONFLICT")
        when = datetime(2026, 9, 14, tzinfo=UTC)
        identity = "source:SRC-PROFILE-CONFLICT"
        observation = make_observation(
            source,
            "PC-1",
            when,
            employer="Conflict Employer",
            identity_key=identity,
            description="private estate",
        )
        make_profile(source, identity, "Conflict Employer", "Premiumsegment", when)
        run, _ = run_classification(when)
        assessment = PremiumSegmentAssessment.objects.get(run=run, posting_observation=observation)
        assert assessment.assessment_status == "REVIEW"
        assert assessment.segment == "UNKNOWN"
        assert assessment.privacy_context == "PRIVATE_RESIDENCE"
        assert PremiumSegmentReviewItem.objects.filter(assessment=assessment).exists()


class PremiumPersistenceInvariantAuditTests(TestCase):
    def valid_assessment(
        self, run: PremiumSegmentRun, observation: PostingObservation, **overrides: object
    ) -> PremiumSegmentAssessment:
        values: dict[str, object] = {
            "run": run,
            "posting_observation": observation,
            "segment": "UNKNOWN",
            "assessment_status": "NO_SUFFICIENT_EVIDENCE",
            "method": "AUDIT",
            "evidence_strength": "NONE",
            "matched_signal_ids": [],
            "matched_fields_and_scopes": [],
            "matched_evidence": [],
            "prohibited_inferences": [],
            "privacy_context": "PUBLIC_OR_NON_RESIDENTIAL",
            "evidence": {"audit": True},
        }
        values.update(overrides)
        return PremiumSegmentAssessment(**values)

    def test_database_rejects_invalid_status_segment_and_run_integrity(self) -> None:
        source = make_source("SRC-DB-INTEGRITY")
        when = datetime(2026, 9, 15, tzinfo=UTC)
        observation = make_observation(source, "DB-1", when)
        run = empty_run(when)
        invalid = self.valid_assessment(
            run,
            observation,
            segment="UNKNOWN",
            assessment_status="CLASSIFIED",
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            PremiumSegmentAssessment.objects.bulk_create([invalid])
        bad_run = PremiumSegmentRun(
            as_of=when,
            classifier_version="premium-segment-v0.1",
            normalizer_version="premium-normalizer-v0.1",
            taxonomy_version="research-v0.4",
            taxonomy_sha256="x" * 64,
            configuration={"audit": True},
            input_fingerprint="short",
            status="SUCCEEDED",
            started_at=when,
            finished_at=when - timedelta(seconds=1),
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            PremiumSegmentRun.objects.bulk_create([bad_run])

    def test_cross_observation_green_and_nonreview_review_item_are_rejected(self) -> None:
        source = make_source("SRC-CROSS-OBJECT")
        when = datetime(2026, 9, 16, tzinfo=UTC)
        first = make_observation(source, "X-1", when)
        second = make_observation(source, "X-2", when)
        green = GreenRelevanceAssessment.objects.get(posting_observation=second)
        run = empty_run(when)
        assessment = self.valid_assessment(run, first, green_relevance_assessment=green)
        with pytest.raises(ValidationError):
            assessment.save()
        valid = self.valid_assessment(run, first)
        valid.save()
        with pytest.raises(ValidationError):
            PremiumSegmentReviewItem.objects.create(
                assessment=valid,
                reason="invalid",
                conflicting_or_insufficient_evidence=[],
            )

    def test_duplicate_profile_and_malformed_hash_are_rejected_by_postgresql(self) -> None:
        source = make_source("SRC-PROFILE-DB")
        when = datetime(2026, 9, 17, tzinfo=UTC)
        kwargs = {
            "source": source,
            "employer_identity_key": "source:SRC-PROFILE-DB",
            "employer_name": "Profile Employer",
            "evidence_text": "Premiumsegment",
            "evidence_type": "PREMIUM_PROFILE",
            "source_url": f"https://{source.domain}/profile",
            "available_at": when,
            "raw_sha256": "a" * 64,
            "evidence_version": "v1",
            "provenance": {},
            "created_at": when,
        }
        with pytest.raises(IntegrityError), transaction.atomic():
            EmployerProfileEvidence.objects.bulk_create(
                [EmployerProfileEvidence(**kwargs), EmployerProfileEvidence(**kwargs)]
            )
        malformed = dict(kwargs)
        malformed["raw_sha256"] = "not-a-sha"
        with pytest.raises(IntegrityError), transaction.atomic():
            EmployerProfileEvidence.objects.bulk_create([EmployerProfileEvidence(**malformed)])

    def test_all_new_evidence_layers_are_append_only(self) -> None:
        source = make_source("SRC-APPEND-ONLY")
        when = datetime(2026, 9, 18, tzinfo=UTC)
        identity = "source:SRC-APPEND-ONLY"
        observation = make_observation(
            source,
            "AO-1",
            when,
            description="private estate Premiumsegment",
            identity_key=identity,
        )
        profile = make_profile(source, identity, "Fixture Employer", "Premiumsegment", when)
        run, _ = run_classification(when)
        assessment = PremiumSegmentAssessment.objects.get(run=run, posting_observation=observation)
        review = PremiumSegmentReviewItem.objects.get(assessment=assessment)
        link = PremiumSegmentAssessmentEmployerEvidence.objects.get(assessment=assessment)
        for instance in (profile, run, assessment, review, link):
            with pytest.raises(Exception):
                instance.delete()
            with pytest.raises(Exception):
                instance.save()
            with pytest.raises(Exception):
                type(instance).objects.filter(pk=instance.pk).update(created_at=when)
            with pytest.raises(Exception):
                type(instance).objects.filter(pk=instance.pk).delete()
            with pytest.raises(Exception):
                type(instance).objects.bulk_update([instance], ["created_at"])

    def test_partial_assessment_failure_rolls_back_run_and_assessments(self) -> None:
        source = make_source("SRC-ROLLBACK")
        when = datetime(2026, 9, 19, tzinfo=UTC)
        make_observation(source, "R-1", when)
        make_observation(source, "R-2", when)
        original_create = PremiumSegmentAssessment.objects.create
        calls = 0

        def flaky_create(**kwargs: object) -> PremiumSegmentAssessment:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("synthetic persistence failure")
            return original_create(**kwargs)

        with patch.object(PremiumSegmentAssessment.objects, "create", side_effect=flaky_create):
            with pytest.raises(RuntimeError, match="synthetic persistence failure"):
                run_classification(when)
        assert PremiumSegmentRun.objects.count() == 0
        assert PremiumSegmentAssessment.objects.count() == 0

    def test_command_failure_is_nonzero_and_does_not_echo_private_input(self) -> None:
        source = make_source("SRC-COMMAND-FAIL")
        when = datetime(2026, 9, 20, tzinfo=UTC)
        street = "Confidentialstrasse 99"
        make_observation(
            source,
            "CF-1",
            when,
            description=street,
            contract_overrides={"raw_payload_sha256": "0" * 64},
        )
        with pytest.raises(CommandError) as captured:
            call_command("classify_premium_segments", "--as-of", when.isoformat())
        assert street not in str(captured.value)
        assert "classification failed" in str(captured.value)


class PremiumRunConcurrencyAuditTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_exact_run_creation_is_idempotent_and_complete(self) -> None:
        source = make_source("SRC-CONCURRENT")
        when = datetime(2026, 9, 21, tzinfo=UTC)
        make_observation(source, "CC-1", when)
        barrier = threading.Barrier(2)

        def worker() -> str:
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                run, _ = run_classification(when)
                return str(run.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            run_ids = list(executor.map(lambda _: worker(), range(2)))
        assert len(set(run_ids)) == 1
        assert PremiumSegmentRun.objects.count() == 1
        run = PremiumSegmentRun.objects.get()
        assert (
            PremiumSegmentAssessment.objects.filter(run=run).count()
            == run.observations_considered
            == 1
        )
