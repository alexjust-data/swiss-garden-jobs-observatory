from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from core.hashing import sha256_file
from observations.models import GreenRelevanceAssessment, Posting, PostingObservation

from .models import (
    EmployerProfileEvidence,
    PremiumSegmentAssessment,
    PremiumSegmentReviewItem,
    PremiumSegmentRun,
)

CLASSIFIER_VERSION = "premium-segment-v0.1"
NORMALIZER_VERSION = "premium-normalizer-v0.1"
TAXONOMY_VERSION = "research-v0.4"
TAXONOMY_PATH = (
    Path(settings.BASE_DIR) / "docs" / "research" / "v0_4" / "premium_signal_taxonomy.csv"
)
PRIVACY_POLICY_VERSION = "location-privacy-v0.1"
EXPECTED_HEADERS = (
    "signal_id",
    "signal_group",
    "search_term",
    "evidence_scope",
    "base_weight",
    "default_segment",
    "notes",
)
STRONG_PREMIUM = frozenset({"P001", "P002", "P003", "P005"})
QUALIFIED_PREMIUM_REVIEW = frozenset({"P004"})
ESTATE_DIRECT = frozenset({"P006", "P007", "P009", "P010", "P011"})
WEAK_PRIVATE = frozenset({"P008", "P024"})
ESTATE_ROLE = frozenset({"P012", "P013", "P014"})
DESIGN_AUXILIARY = frozenset({"P015", "P016", "P017", "P018", "P019", "P020"})
HOUSEHOLD_REQUIREMENT = frozenset({"P021", "P022", "P023"})
PROHIBITED = frozenset({"N001", "N002"})

CONFIGURATION: dict[str, object] = {
    "decision_table": "premium-segment-decision-table-v0.1",
    "strong_premium": sorted(STRONG_PREMIUM),
    "qualified_premium_review": sorted(QUALIFIED_PREMIUM_REVIEW),
    "estate_direct": sorted(ESTATE_DIRECT),
    "weak_private": sorted(WEAK_PRIVATE),
    "estate_role": sorted(ESTATE_ROLE),
    "design_auxiliary": sorted(DESIGN_AUXILIARY),
    "household_requirement": sorted(HOUSEHOLD_REQUIREMENT),
    "prohibited": sorted(PROHIBITED),
    "confidence_semantics": "categorical_evidence_strength_not_probability",
}


class PremiumSegmentError(ValueError):
    pass


@dataclass(frozen=True)
class PremiumSignalDefinition:
    signal_id: str
    signal_group: str
    search_term: str
    evidence_scope: str
    base_weight: Decimal
    default_segment: str
    notes: str


@dataclass(frozen=True)
class EmployerEvidenceInput:
    evidence_id: str
    evidence_text: str


@dataclass(frozen=True)
class PremiumDecision:
    segment: str
    status: str
    method: str
    evidence_strength: str
    matches: tuple[dict[str, str], ...]
    prohibited: tuple[dict[str, str], ...]
    reason_codes: tuple[str, ...]
    privacy_context: str


@dataclass(frozen=True)
class SelectedInput:
    observation: PostingObservation
    green_assessment: GreenRelevanceAssessment | None
    employer_profile: EmployerProfileEvidence | None


def normalize_for_matching(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    controlled = "".join(character if character.isalnum() else " " for character in normalized)
    return " ".join(controlled.split())


def load_taxonomy(path: Path = TAXONOMY_PATH) -> tuple[tuple[PremiumSignalDefinition, ...], str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_HEADERS:
            raise PremiumSegmentError("premium taxonomy headers do not match research v0.4")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if len(rows) != 26 or len({row["signal_id"] for row in rows}) != 26:
        raise PremiumSegmentError("premium taxonomy must contain 26 unique signals")
    signals = tuple(
        PremiumSignalDefinition(
            row["signal_id"],
            row["signal_group"],
            row["search_term"],
            row["evidence_scope"],
            Decimal(row["base_weight"]),
            row["default_segment"],
            row["notes"],
        )
        for row in rows
    )
    return signals, sha256_file(path)


def _safe_match(
    signal: PremiumSignalDefinition, field: str, profile_id: str = ""
) -> dict[str, str]:
    return {
        "signal_id": signal.signal_id,
        "signal_group": signal.signal_group,
        "search_term": signal.search_term,
        "evidence_scope": signal.evidence_scope,
        "matched_field": field,
        "matched_text": signal.search_term,
        "base_weight": str(signal.base_weight),
        "default_segment": signal.default_segment,
        "employer_profile_evidence_id": profile_id,
    }


class PremiumSegmentClassifier:
    def __init__(self, taxonomy_path: Path = TAXONOMY_PATH) -> None:
        self.signals, self.taxonomy_sha256 = load_taxonomy(taxonomy_path)

    def classify_observation(
        self,
        observation: PostingObservation,
        green_result: str,
        employer_profile: EmployerProfileEvidence | None = None,
    ) -> PremiumDecision:
        profiles: tuple[EmployerEvidenceInput, ...] = ()
        if employer_profile:
            profiles = (
                EmployerEvidenceInput(str(employer_profile.pk), employer_profile.evidence_text),
            )
        return self.classify(
            title=observation.title,
            description=observation.description_html,
            responsibilities=observation.responsibilities_html,
            qualifications=observation.qualifications_html,
            benefits=observation.benefits_html,
            green_result=green_result,
            employer_evidence=profiles,
        )

    def classify(
        self,
        *,
        title: str = "",
        description: str = "",
        responsibilities: str = "",
        qualifications: str = "",
        benefits: str = "",
        green_result: str,
        employer_evidence: tuple[EmployerEvidenceInput, ...] = (),
        inference_evidence: str = "",
    ) -> PremiumDecision:
        if green_result != GreenRelevanceAssessment.Result.GREEN_CONFIRMED.value:
            return PremiumDecision(
                PremiumSegmentAssessment.Segment.UNKNOWN.value,
                PremiumSegmentAssessment.Status.SKIPPED_NOT_GREEN.value,
                "GREEN_RELEVANCE_GATE",
                PremiumSegmentAssessment.EvidenceStrength.NONE.value,
                (),
                (),
                ("GREEN_CONFIRMED_REQUIRED",),
                PremiumSegmentAssessment.PrivacyContext.PUBLIC_OR_NON_RESIDENTIAL.value,
            )
        surfaces = {
            "TITLE": normalize_for_matching(title),
            "DESCRIPTION": normalize_for_matching(description),
            "RESPONSIBILITIES": normalize_for_matching(responsibilities),
            "QUALIFICATIONS": normalize_for_matching(qualifications),
            "BENEFITS": normalize_for_matching(benefits),
        }
        normalized_inference = normalize_for_matching(inference_evidence)
        matches: list[dict[str, str]] = []
        prohibited: list[dict[str, str]] = []
        for signal in self.signals:
            needle = normalize_for_matching(signal.search_term)
            if signal.evidence_scope == "INFERENCE":
                if needle and needle in normalized_inference:
                    prohibited.append(_safe_match(signal, "PROHIBITED_INFERENCE"))
                continue
            for field, haystack in surfaces.items():
                if needle and needle in haystack:
                    matches.append(_safe_match(signal, field))
                    break
            if "EMPLOYER" in signal.evidence_scope:
                for profile in employer_evidence:
                    if needle and needle in normalize_for_matching(profile.evidence_text):
                        matches.append(_safe_match(signal, "EMPLOYER_PROFILE", profile.evidence_id))
                        break
        ids = {match["signal_id"] for match in matches}
        premium = ids & STRONG_PREMIUM
        estate = ids & ESTATE_DIRECT
        roles = ids & ESTATE_ROLE
        weak = ids & WEAK_PRIVATE
        qualified = ids & QUALIFIED_PREMIUM_REVIEW
        auxiliary = ids & (DESIGN_AUXILIARY | HOUSEHOLD_REQUIREMENT)
        public = PremiumSegmentAssessment.PrivacyContext.PUBLIC_OR_NON_RESIDENTIAL.value
        private = PremiumSegmentAssessment.PrivacyContext.PRIVATE_RESIDENCE.value
        if premium and (estate or roles):
            return PremiumDecision(
                PremiumSegmentAssessment.Segment.UNKNOWN.value,
                PremiumSegmentAssessment.Status.REVIEW.value,
                "CONFLICTING_EXPLICIT_SEGMENTS",
                PremiumSegmentAssessment.EvidenceStrength.STRONG.value,
                tuple(matches),
                tuple(prohibited),
                ("PREMIUM_AND_ESTATE_CONFLICT",),
                private,
            )
        if estate or roles:
            return PremiumDecision(
                PremiumSegmentAssessment.Segment.PRIVATE_ESTATE_DIRECT.value,
                PremiumSegmentAssessment.Status.CLASSIFIED.value,
                "EXPLICIT_ESTATE_SIGNAL" if estate else "GREEN_CORROBORATED_ESTATE_ROLE",
                PremiumSegmentAssessment.EvidenceStrength.STRONG.value
                if estate
                else PremiumSegmentAssessment.EvidenceStrength.MODERATE.value,
                tuple(matches),
                tuple(prohibited),
                ("PRIVATE_ESTATE_EVIDENCE",),
                private,
            )
        if premium:
            matched_profile = any(
                match["signal_id"] in premium and match["matched_field"] == "EMPLOYER_PROFILE"
                for match in matches
            )
            return PremiumDecision(
                PremiumSegmentAssessment.Segment.PRIVATE_RESIDENTIAL_PREMIUM.value,
                PremiumSegmentAssessment.Status.CLASSIFIED.value,
                "EMPLOYER_PROFILE_SIGNAL" if matched_profile else "EXPLICIT_JOB_SIGNAL",
                PremiumSegmentAssessment.EvidenceStrength.MODERATE.value
                if matched_profile
                else PremiumSegmentAssessment.EvidenceStrength.STRONG.value,
                tuple(matches),
                tuple(prohibited),
                ("EXPLICIT_PREMIUM_EVIDENCE",),
                public,
            )
        if qualified:
            return PremiumDecision(
                PremiumSegmentAssessment.Segment.UNKNOWN.value,
                PremiumSegmentAssessment.Status.REVIEW.value,
                "QUALIFIED_PREMIUM_SIGNAL",
                PremiumSegmentAssessment.EvidenceStrength.MODERATE.value,
                tuple(matches),
                tuple(prohibited),
                ("P004_REQUIRES_CORROBORATION",),
                public,
            )
        if weak:
            return PremiumDecision(
                PremiumSegmentAssessment.Segment.PRIVATE_RESIDENTIAL_STANDARD.value,
                PremiumSegmentAssessment.Status.CLASSIFIED.value,
                "WEAK_PRIVATE_SIGNAL",
                PremiumSegmentAssessment.EvidenceStrength.WEAK.value,
                tuple(matches),
                tuple(prohibited),
                ("PRIVATE_NON_PREMIUM_EVIDENCE",),
                private,
            )
        reason = "AUXILIARY_SIGNAL_INSUFFICIENT" if auxiliary else "NO_PREMIUM_TAXONOMY_SIGNAL"
        if prohibited and not matches:
            reason = "PROHIBITED_INFERENCE_ONLY"
        return PremiumDecision(
            PremiumSegmentAssessment.Segment.UNKNOWN.value,
            PremiumSegmentAssessment.Status.NO_SUFFICIENT_EVIDENCE.value,
            "NO_AUTOMATIC_CLASSIFICATION",
            PremiumSegmentAssessment.EvidenceStrength.NONE.value,
            tuple(matches),
            tuple(prohibited),
            (reason,),
            public,
        )


def _contract_valid(observation: PostingObservation) -> bool:
    contract = observation.contract_payload or {}
    return (
        contract.get("schema_version") == "1.2"
        and contract.get("observation_status") == "ACTIVE"
        and bool(contract.get("raw_payload_sha256"))
    )


def select_inputs(as_of: datetime) -> list[SelectedInput]:
    latest = PostingObservation.objects.filter(
        posting_id=OuterRef("pk"), observation_status="ACTIVE", observed_at__lte=as_of
    ).order_by("-observed_at", "-pk")
    observation_ids = (
        Posting.objects.filter(first_seen_at__lte=as_of)
        .annotate(selected_observation_id=Subquery(latest.values("id")[:1]))
        .exclude(selected_observation_id=None)
        .values_list("selected_observation_id", flat=True)
    )
    observations = list(
        PostingObservation.objects.filter(pk__in=observation_ids).select_related(
            "source", "posting"
        )
    )
    profiles_by_employer: dict[str, list[EmployerProfileEvidence]] = {}
    for profile in EmployerProfileEvidence.objects.filter(available_at__lte=as_of):
        profiles_by_employer.setdefault(normalize_for_matching(profile.employer_name), []).append(
            profile
        )
    selected: list[SelectedInput] = []
    for observation in sorted(observations, key=lambda item: str(item.pk)):
        if not _contract_valid(observation):
            continue
        green = (
            GreenRelevanceAssessment.objects.filter(
                posting_observation=observation, created_at__lte=as_of
            )
            .order_by("-created_at", "-pk")
            .first()
        )
        profiles = profiles_by_employer.get(
            normalize_for_matching(observation.hiring_organization), []
        )
        profile = max(profiles, key=lambda item: (item.available_at, str(item.pk)), default=None)
        selected.append(SelectedInput(observation, green, profile))
    return selected


def input_fingerprint(
    as_of: datetime,
    classifier_version: str,
    normalizer_version: str,
    taxonomy_sha256: str,
    inputs: list[SelectedInput],
) -> str:
    payload = {
        "as_of": as_of.isoformat(),
        "classifier_version": classifier_version,
        "normalizer_version": normalizer_version,
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_sha256": taxonomy_sha256,
        "configuration": CONFIGURATION,
        "inputs": [
            {
                "observation_id": str(item.observation.pk),
                "green_assessment_id": str(item.green_assessment.pk)
                if item.green_assessment
                else None,
                "employer_profile_evidence_id": str(item.employer_profile.pk)
                if item.employer_profile
                else None,
            }
            for item in inputs
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _evidence(
    item: SelectedInput, decision: PremiumDecision, normalizer_version: str
) -> dict[str, object]:
    return {
        "posting_observation_id": str(item.observation.pk),
        "green_relevance_assessment_id": str(item.green_assessment.pk)
        if item.green_assessment
        else None,
        "employer_profile_evidence_id": str(item.employer_profile.pk)
        if item.employer_profile
        else None,
        "reason_codes": list(decision.reason_codes),
        "normalization": normalizer_version,
        "matching": "LITERAL_PHRASE_SCOPE_ENFORCED",
        "confidence_semantics": "categorical_evidence_strength_not_probability",
        "privacy": {
            "context": decision.privacy_context,
            "policy_version": PRIVACY_POLICY_VERSION,
            "exact_residential_address_copied": False,
        },
    }


@transaction.atomic
def run_classification(
    as_of: datetime,
    *,
    classifier_version: str = CLASSIFIER_VERSION,
    normalizer_version: str = NORMALIZER_VERSION,
    taxonomy_path: Path = TAXONOMY_PATH,
) -> tuple[PremiumSegmentRun, bool]:
    classifier = PremiumSegmentClassifier(taxonomy_path)
    inputs = select_inputs(as_of)
    fingerprint = input_fingerprint(
        as_of, classifier_version, normalizer_version, classifier.taxonomy_sha256, inputs
    )
    existing = PremiumSegmentRun.objects.filter(
        as_of=as_of,
        classifier_version=classifier_version,
        normalizer_version=normalizer_version,
        taxonomy_sha256=classifier.taxonomy_sha256,
        input_fingerprint=fingerprint,
        status=PremiumSegmentRun.Status.SUCCEEDED,
    ).first()
    if existing:
        return existing, True
    decisions = [
        classifier.classify_observation(
            item.observation,
            item.green_assessment.result if item.green_assessment else "MISSING",
            item.employer_profile,
        )
        for item in inputs
    ]
    statuses = {
        value: sum(decision.status == value for decision in decisions)
        for value in PremiumSegmentAssessment.Status.values
    }
    segments = {
        value: sum(decision.segment == value for decision in decisions)
        for value in PremiumSegmentAssessment.Segment.values
    }
    now = timezone.now()
    run = PremiumSegmentRun.objects.create(
        as_of=as_of,
        classifier_version=classifier_version,
        normalizer_version=normalizer_version,
        taxonomy_version=TAXONOMY_VERSION,
        taxonomy_sha256=classifier.taxonomy_sha256,
        configuration=CONFIGURATION,
        input_fingerprint=fingerprint,
        observations_considered=len(inputs),
        green_confirmed_eligible=sum(
            item.green_assessment is not None
            and item.green_assessment.result
            == GreenRelevanceAssessment.Result.GREEN_CONFIRMED.value
            for item in inputs
        ),
        classified_count=statuses[PremiumSegmentAssessment.Status.CLASSIFIED.value],
        review_count=statuses[PremiumSegmentAssessment.Status.REVIEW.value],
        no_sufficient_evidence_count=statuses[
            PremiumSegmentAssessment.Status.NO_SUFFICIENT_EVIDENCE.value
        ],
        skipped_not_green_count=statuses[PremiumSegmentAssessment.Status.SKIPPED_NOT_GREEN.value],
        private_residential_standard_count=segments[
            PremiumSegmentAssessment.Segment.PRIVATE_RESIDENTIAL_STANDARD.value
        ],
        private_residential_premium_count=segments[
            PremiumSegmentAssessment.Segment.PRIVATE_RESIDENTIAL_PREMIUM.value
        ],
        private_estate_direct_count=segments[
            PremiumSegmentAssessment.Segment.PRIVATE_ESTATE_DIRECT.value
        ],
        unknown_count=segments[PremiumSegmentAssessment.Segment.UNKNOWN.value],
        prohibited_inference_only_count=sum(
            "PROHIBITED_INFERENCE_ONLY" in decision.reason_codes for decision in decisions
        ),
        status=PremiumSegmentRun.Status.SUCCEEDED,
        started_at=now,
        finished_at=now,
    )
    for item, decision in zip(inputs, decisions, strict=True):
        assessment = PremiumSegmentAssessment.objects.create(
            run=run,
            posting_observation=item.observation,
            green_relevance_assessment=item.green_assessment,
            employer_profile_evidence=item.employer_profile,
            segment=decision.segment,
            assessment_status=decision.status,
            method=decision.method,
            evidence_strength=decision.evidence_strength,
            matched_signal_ids=sorted({match["signal_id"] for match in decision.matches}),
            matched_fields_and_scopes=[
                {
                    "signal_id": match["signal_id"],
                    "field": match["matched_field"],
                    "scope": match["evidence_scope"],
                }
                for match in decision.matches
            ],
            matched_evidence=list(decision.matches),
            prohibited_inferences=list(decision.prohibited),
            privacy_context=decision.privacy_context,
            evidence=_evidence(item, decision, normalizer_version),
        )
        if decision.status == PremiumSegmentAssessment.Status.REVIEW.value:
            PremiumSegmentReviewItem.objects.create(
                assessment=assessment,
                reason=decision.reason_codes[0],
                conflicting_or_insufficient_evidence=list(decision.matches),
            )
    return run, False
