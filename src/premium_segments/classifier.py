from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.hashing import sha256_file
from observations.contracts import (
    PostingObservationContractError,
    validate_posting_observation_contract,
)
from observations.models import (
    GreenRelevanceAssessment,
    PostingObservation,
)
from observations.pit_selection import PIT_SELECTION_VERSION, select_posting_states
from observations.review import EffectiveGreenResult, effective_green_result

from .models import (
    EmployerProfileEvidence,
    PremiumSegmentAssessment,
    PremiumSegmentAssessmentEmployerEvidence,
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

GREEN_CONFIRMED = "GREEN_CONFIRMED"
SEGMENT_UNKNOWN = "UNKNOWN"
SEGMENT_PRIVATE_RESIDENTIAL_STANDARD = "PRIVATE_RESIDENTIAL_STANDARD"
SEGMENT_PRIVATE_RESIDENTIAL_PREMIUM = "PRIVATE_RESIDENTIAL_PREMIUM"
SEGMENT_PRIVATE_ESTATE_DIRECT = "PRIVATE_ESTATE_DIRECT"
STATUS_CLASSIFIED = "CLASSIFIED"
STATUS_REVIEW = "REVIEW"
STATUS_NO_SUFFICIENT_EVIDENCE = "NO_SUFFICIENT_EVIDENCE"
STATUS_SKIPPED_NOT_GREEN = "SKIPPED_NOT_GREEN"
EVIDENCE_NONE = "NONE"
EVIDENCE_WEAK = "WEAK"
EVIDENCE_MODERATE = "MODERATE"
EVIDENCE_STRONG = "STRONG"
PRIVACY_PUBLIC_OR_NON_RESIDENTIAL = "PUBLIC_OR_NON_RESIDENTIAL"
PRIVACY_PRIVATE_RESIDENCE = "PRIVATE_RESIDENCE"
GREEN_CLASSIFIER_VERSION = "green-relevance-v0.1"
GREEN_TAXONOMY_VERSION = "research-v0.4"
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
JOB_SURFACES = frozenset({"TITLE", "DESCRIPTION", "RESPONSIBILITIES", "QUALIFICATIONS", "BENEFITS"})
SCOPE_SURFACES = {
    "JOB": JOB_SURFACES,
    "JOB_OR_EMPLOYER": JOB_SURFACES | {"EMPLOYER_PROFILE"},
    "JOB_OR_SOURCE": JOB_SURFACES,
    "TITLE_OR_TEXT": JOB_SURFACES,
    "INFERENCE": frozenset({"PROHIBITED_INFERENCE"}),
}
URL_PATTERN = re.compile(r"(?i)\b(?:https?://|www\.)\S+")

CONFIGURATION: dict[str, object] = {
    "pit_selection_version": PIT_SELECTION_VERSION,
    "decision_table": "premium-segment-decision-table-v0.1",
    "strong_premium": sorted(STRONG_PREMIUM),
    "qualified_premium_review": sorted(QUALIFIED_PREMIUM_REVIEW),
    "estate_direct": sorted(ESTATE_DIRECT),
    "weak_private": sorted(WEAK_PRIVATE),
    "estate_role": sorted(ESTATE_ROLE),
    "design_auxiliary": sorted(DESIGN_AUXILIARY),
    "household_requirement": sorted(HOUSEHOLD_REQUIREMENT),
    "prohibited": sorted(PROHIBITED),
    "scope_surfaces": {key: sorted(value) for key, value in SCOPE_SURFACES.items()},
    "source_profile_support": False,
    "employer_profile_semantics": "cumulative_assertions_bound_to_explicit_identity",
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
    effective_green: EffectiveGreenResult
    employer_profiles: tuple[EmployerProfileEvidence, ...]
    lifecycle_event_id: str | None
    lifecycle_state: str


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript", "template"}:
            self.suppressed_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript", "template"}:
            self.suppressed_depth = max(0, self.suppressed_depth - 1)

    def handle_data(self, data: str) -> None:
        if self.suppressed_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


def normalize_for_matching(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    controlled = "".join(character if character.isalnum() else " " for character in normalized)
    return " ".join(controlled.split())


def visible_text(value: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(value)
    parser.close()
    return URL_PATTERN.sub(" ", parser.text())


def phrase_matches(needle: str, haystack: str) -> bool:
    needle_tokens = normalize_for_matching(needle).split()
    haystack_tokens = normalize_for_matching(haystack).split()
    if not needle_tokens or len(needle_tokens) > len(haystack_tokens):
        return False
    width = len(needle_tokens)
    return any(
        haystack_tokens[index : index + width] == needle_tokens
        for index in range(len(haystack_tokens) - width + 1)
    )


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
        unknown_scopes = {signal.evidence_scope for signal in self.signals} - SCOPE_SURFACES.keys()
        if unknown_scopes:
            raise PremiumSegmentError(f"unsupported evidence scopes: {sorted(unknown_scopes)}")

    def classify_observation(
        self,
        observation: PostingObservation,
        green_result: str,
        employer_profiles: tuple[EmployerProfileEvidence, ...] = (),
    ) -> PremiumDecision:
        profiles = tuple(
            EmployerEvidenceInput(str(profile.pk), profile.evidence_text)
            for profile in employer_profiles
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
        if green_result != GREEN_CONFIRMED:
            return PremiumDecision(
                SEGMENT_UNKNOWN,
                STATUS_SKIPPED_NOT_GREEN,
                "GREEN_RELEVANCE_GATE",
                EVIDENCE_NONE,
                (),
                (),
                ("GREEN_CONFIRMED_REQUIRED",),
                PRIVACY_PUBLIC_OR_NON_RESIDENTIAL,
            )
        surfaces = {
            "TITLE": visible_text(title),
            "DESCRIPTION": visible_text(description),
            "RESPONSIBILITIES": visible_text(responsibilities),
            "QUALIFICATIONS": visible_text(qualifications),
            "BENEFITS": visible_text(benefits),
        }
        inference_surface = visible_text(inference_evidence)
        matches: list[dict[str, str]] = []
        prohibited: list[dict[str, str]] = []
        for signal in self.signals:
            allowed_surfaces = SCOPE_SURFACES[signal.evidence_scope]
            if signal.evidence_scope == "INFERENCE":
                if phrase_matches(signal.search_term, inference_surface):
                    prohibited.append(_safe_match(signal, "PROHIBITED_INFERENCE"))
                continue
            for field in sorted(JOB_SURFACES & allowed_surfaces):
                if phrase_matches(signal.search_term, surfaces[field]):
                    matches.append(_safe_match(signal, field))
                    break
            if "EMPLOYER_PROFILE" in allowed_surfaces:
                for profile in employer_evidence:
                    if phrase_matches(signal.search_term, visible_text(profile.evidence_text)):
                        matches.append(_safe_match(signal, "EMPLOYER_PROFILE", profile.evidence_id))
        ids = {match["signal_id"] for match in matches}
        premium = ids & STRONG_PREMIUM
        estate = ids & ESTATE_DIRECT
        roles = ids & ESTATE_ROLE
        weak = ids & WEAK_PRIVATE
        qualified = ids & QUALIFIED_PREMIUM_REVIEW
        auxiliary = ids & (DESIGN_AUXILIARY | HOUSEHOLD_REQUIREMENT)
        public = PRIVACY_PUBLIC_OR_NON_RESIDENTIAL
        private = PRIVACY_PRIVATE_RESIDENCE
        if premium and (estate or roles):
            return PremiumDecision(
                SEGMENT_UNKNOWN,
                STATUS_REVIEW,
                "CONFLICTING_EXPLICIT_SEGMENTS",
                EVIDENCE_STRONG,
                tuple(matches),
                tuple(prohibited),
                ("PREMIUM_AND_ESTATE_CONFLICT",),
                private,
            )
        if estate or roles:
            return PremiumDecision(
                SEGMENT_PRIVATE_ESTATE_DIRECT,
                STATUS_CLASSIFIED,
                "EXPLICIT_ESTATE_SIGNAL" if estate else "GREEN_CORROBORATED_ESTATE_ROLE",
                EVIDENCE_STRONG if estate else EVIDENCE_MODERATE,
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
                SEGMENT_PRIVATE_RESIDENTIAL_PREMIUM,
                STATUS_CLASSIFIED,
                "EMPLOYER_PROFILE_SIGNAL" if matched_profile else "EXPLICIT_JOB_SIGNAL",
                EVIDENCE_MODERATE if matched_profile else EVIDENCE_STRONG,
                tuple(matches),
                tuple(prohibited),
                ("EXPLICIT_PREMIUM_EVIDENCE",),
                private,
            )
        if qualified:
            return PremiumDecision(
                SEGMENT_UNKNOWN,
                STATUS_REVIEW,
                "QUALIFIED_PREMIUM_SIGNAL",
                EVIDENCE_MODERATE,
                tuple(matches),
                tuple(prohibited),
                ("P004_REQUIRES_CORROBORATION",),
                public,
            )
        if weak:
            return PremiumDecision(
                SEGMENT_PRIVATE_RESIDENTIAL_STANDARD,
                STATUS_CLASSIFIED,
                "WEAK_PRIVATE_SIGNAL",
                EVIDENCE_WEAK,
                tuple(matches),
                tuple(prohibited),
                ("PRIVATE_NON_PREMIUM_EVIDENCE",),
                private,
            )
        reason = "AUXILIARY_SIGNAL_INSUFFICIENT" if auxiliary else "NO_PREMIUM_TAXONOMY_SIGNAL"
        if prohibited and not matches:
            reason = "PROHIBITED_INFERENCE_ONLY"
        return PremiumDecision(
            SEGMENT_UNKNOWN,
            STATUS_NO_SUFFICIENT_EVIDENCE,
            "NO_AUTOMATIC_CLASSIFICATION",
            EVIDENCE_NONE,
            tuple(matches),
            tuple(prohibited),
            (reason,),
            public,
        )


def _validate_contract_integrity(observation: PostingObservation) -> None:
    contract = observation.contract_payload or {}
    try:
        validate_posting_observation_contract(contract)
    except PostingObservationContractError as exc:
        raise PremiumSegmentError(
            f"observation {observation.pk} failed frozen contract validation"
        ) from exc
    observed_at = parse_datetime(str(contract.get("observed_at", "")))
    raw_sha256 = str(contract.get("raw_payload_sha256", ""))
    expected = {
        "source_id": str(observation.source.pk),
        "source_native_id": observation.source_posting_id,
        "observation_status": observation.observation_status,
        "canonical_url": observation.canonical_url,
        "raw_title": observation.title,
        "collector_run_id": str(observation.collection_run.pk),
    }
    mismatches = [key for key, value in expected.items() if contract.get(key) != value]
    if observation.observation_status != "ACTIVE":
        mismatches.append("model_observation_status")
    if observed_at is None or observed_at != observation.observed_at:
        mismatches.append("observed_at")
    if not re.fullmatch(r"[0-9a-f]{64}", raw_sha256):
        mismatches.append("raw_payload_sha256_format")
    if raw_sha256 != observation.raw_artifact.sha256_digest:
        mismatches.append("raw_payload_sha256_link")
    if mismatches:
        raise PremiumSegmentError(
            f"observation {observation.pk} has inconsistent contract provenance: "
            + ", ".join(sorted(set(mismatches)))
        )


def select_inputs(as_of: datetime) -> list[SelectedInput]:
    selected: list[SelectedInput] = []
    for state in select_posting_states(as_of):
        observation = state.observation
        lifecycle_event_id = str(state.lifecycle_event.pk) if state.lifecycle_event else None
        _validate_contract_integrity(observation)
        green = (
            GreenRelevanceAssessment.objects.filter(
                posting_observation=observation,
                classifier_version=GREEN_CLASSIFIER_VERSION,
                taxonomy_version=GREEN_TAXONOMY_VERSION,
                created_at__lte=as_of,
            )
            .order_by("-created_at", "-pk")
            .first()
        )
        identity_key = str(
            (observation.structured_payload or {}).get("employer_identity_key", "")
        ).strip()
        profiles: tuple[EmployerProfileEvidence, ...] = ()
        if identity_key and observation.hiring_organization.strip():
            candidates = EmployerProfileEvidence.objects.filter(
                source=observation.source,
                employer_identity_key=identity_key,
                available_at__lte=as_of,
            ).order_by("available_at", "created_at", "pk")
            normalized_employer = normalize_for_matching(observation.hiring_organization)
            profiles = tuple(
                profile
                for profile in candidates
                if normalize_for_matching(profile.employer_name) == normalized_employer
            )
        selected.append(
            SelectedInput(
                observation,
                green,
                effective_green_result(green, as_of=as_of),
                profiles,
                lifecycle_event_id,
                state.lifecycle_state,
            )
        )
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
                "effective_green_result": item.effective_green.result,
                "green_review_decision_id": str(item.effective_green.decision.pk)
                if item.effective_green.decision
                else None,
                "employer_profile_evidence_ids": [
                    str(profile.pk) for profile in item.employer_profiles
                ],
                "lifecycle_event_id": item.lifecycle_event_id,
                "lifecycle_state": item.lifecycle_state,
                "pit_selection_version": PIT_SELECTION_VERSION,
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
        "effective_green_result": item.effective_green.result,
        "green_review_decision_id": str(item.effective_green.decision.pk)
        if item.effective_green.decision
        else None,
        "employer_profile_evidence_ids": [str(profile.pk) for profile in item.employer_profiles],
        "lifecycle_event_id": item.lifecycle_event_id,
        "lifecycle_state": item.lifecycle_state,
        "pit_selection_version": PIT_SELECTION_VERSION,
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


def _lock_exact_run(input_fingerprint: str) -> None:
    if connection.vendor != "postgresql":
        return
    lock_key = int.from_bytes(bytes.fromhex(input_fingerprint)[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])


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
    _lock_exact_run(fingerprint)
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
            item.effective_green.result,
            item.employer_profiles,
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
            item.effective_green.result == GREEN_CONFIRMED for item in inputs
        ),
        classified_count=statuses[STATUS_CLASSIFIED],
        review_count=statuses[STATUS_REVIEW],
        no_sufficient_evidence_count=statuses[STATUS_NO_SUFFICIENT_EVIDENCE],
        skipped_not_green_count=statuses[STATUS_SKIPPED_NOT_GREEN],
        private_residential_standard_count=segments[SEGMENT_PRIVATE_RESIDENTIAL_STANDARD],
        private_residential_premium_count=segments[SEGMENT_PRIVATE_RESIDENTIAL_PREMIUM],
        private_estate_direct_count=segments[SEGMENT_PRIVATE_ESTATE_DIRECT],
        unknown_count=segments[SEGMENT_UNKNOWN],
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
            green_review_decision=item.effective_green.decision,
            effective_green_result=item.effective_green.result,
            employer_profile_evidence=(
                item.employer_profiles[0] if len(item.employer_profiles) == 1 else None
            ),
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
        PremiumSegmentAssessmentEmployerEvidence.objects.bulk_create(
            [
                PremiumSegmentAssessmentEmployerEvidence(
                    assessment=assessment,
                    employer_profile_evidence=profile,
                )
                for profile in item.employer_profiles
            ]
        )
        if decision.status == STATUS_REVIEW:
            PremiumSegmentReviewItem.objects.create(
                assessment=assessment,
                reason=decision.reason_codes[0],
                conflicting_or_insufficient_evidence=list(decision.matches),
            )
    return run, False
