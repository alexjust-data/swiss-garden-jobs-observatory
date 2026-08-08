from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from core.hashing import sha256_file
from observations.models import PostingObservation

CLASSIFIER_VERSION = "green-relevance-v0.1"
TAXONOMY_VERSION = "research-v0.4"
TAXONOMY_PATH = Path(settings.BASE_DIR) / "docs" / "research" / "v0_4" / "role_search_taxonomy.csv"
EXPECTED_HEADERS = (
    "term_id",
    "canonical_role_family",
    "canonical_specialization",
    "search_term_de",
    "term_type",
    "include_default",
    "public_relevance",
    "default_access_level_hint",
    "notes",
)
SUPPORTED_TYPES = {
    "TITLE",
    "TITLE_OR_TEXT",
    "HIDDEN_PUBLIC_TITLE",
    "TEXT_SIGNAL",
    "ORGANIZATION_SIGNAL",
    "EXCLUSION",
}


class GreenRelevanceError(ValueError):
    pass


@dataclass(frozen=True)
class TaxonomyTerm:
    term_id: str
    search_term: str
    term_type: str
    include_default: str
    public_relevance: str


@dataclass(frozen=True)
class GreenRelevanceDecision:
    result: str
    matched_positive_terms: list[dict[str, str]]
    matched_conditional_terms: list[dict[str, str]]
    matched_exclusion_terms: list[dict[str, str]]
    evidence: dict[str, object]


def normalize_for_matching(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def load_taxonomy(path: Path = TAXONOMY_PATH) -> tuple[list[TaxonomyTerm], str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_HEADERS:
            raise GreenRelevanceError("role taxonomy headers do not match research v0.4")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if len(rows) != 53:
        raise GreenRelevanceError(f"role taxonomy must contain 53 terms, found {len(rows)}")
    terms = [
        TaxonomyTerm(
            term_id=row["term_id"],
            search_term=row["search_term_de"],
            term_type=row["term_type"],
            include_default=row["include_default"],
            public_relevance=row["public_relevance"],
        )
        for row in rows
    ]
    if len({term.term_id for term in terms}) != len(terms):
        raise GreenRelevanceError("role taxonomy term IDs must be unique")
    if {term.term_type for term in terms} - SUPPORTED_TYPES:
        raise GreenRelevanceError("role taxonomy contains unsupported term types")
    return terms, sha256_file(path)


def _evidence(term: TaxonomyTerm, surface: str) -> dict[str, str]:
    return {
        "term_id": term.term_id,
        "search_term": term.search_term,
        "surface": surface,
        "matched_text": term.search_term,
        "term_type": term.term_type,
        "include_default": term.include_default,
        "public_relevance": term.public_relevance,
    }


class GreenRelevanceClassifier:
    def __init__(self, taxonomy_path: Path = TAXONOMY_PATH) -> None:
        self.terms, self.taxonomy_sha256 = load_taxonomy(taxonomy_path)

    def classify_observation(self, observation: PostingObservation) -> GreenRelevanceDecision:
        return self.classify(
            title=observation.title,
            text="\n".join(
                (
                    observation.description_html,
                    observation.responsibilities_html,
                    observation.qualifications_html,
                    observation.benefits_html,
                )
            ),
            organization=observation.hiring_organization,
        )

    def classify(self, *, title: str, text: str, organization: str) -> GreenRelevanceDecision:
        surfaces = {
            "TITLE": normalize_for_matching(title),
            "TEXT": normalize_for_matching(text),
            "ORGANIZATION": normalize_for_matching(organization),
        }
        positive: list[dict[str, str]] = []
        conditional: list[dict[str, str]] = []
        exclusions: list[dict[str, str]] = []
        for term in self.terms:
            needle = normalize_for_matching(term.search_term)
            targets: tuple[str, ...]
            bucket: list[dict[str, str]]
            if term.term_type == "TITLE":
                targets, bucket = ("TITLE",), positive
            elif term.term_type == "TITLE_OR_TEXT":
                targets, bucket = ("TITLE", "TEXT"), positive
            elif term.term_type == "HIDDEN_PUBLIC_TITLE":
                targets, bucket = ("TITLE",), conditional
            elif term.term_type == "TEXT_SIGNAL":
                targets, bucket = ("TITLE", "TEXT"), conditional
            elif term.term_type == "ORGANIZATION_SIGNAL":
                targets, bucket = ("ORGANIZATION",), conditional
            else:
                targets, bucket = ("TITLE", "TEXT"), exclusions
            for surface in targets:
                if needle in surfaces[surface]:
                    bucket.append(_evidence(term, surface))

        if positive and exclusions:
            result, reasons = "REVIEW", ["POSITIVE_AND_EXCLUSION_CONFLICT"]
        elif positive:
            result, reasons = "GREEN_CONFIRMED", ["STRONG_GREEN_TAXONOMY_SIGNAL"]
        elif exclusions:
            result, reasons = "NOT_GREEN", ["EXCLUSION_WITHOUT_GREEN_SIGNAL"]
        elif any(item["term_type"] == "HIDDEN_PUBLIC_TITLE" for item in conditional):
            result, reasons = "REVIEW", ["HIDDEN_PUBLIC_TITLE_NEEDS_GREEN_TASK"]
        elif any(item["term_type"] == "ORGANIZATION_SIGNAL" for item in conditional):
            result, reasons = "REVIEW", ["ORGANIZATION_SIGNAL_ONLY"]
        elif conditional:
            result, reasons = "REVIEW", ["CONDITIONAL_SIGNAL_ONLY"]
        else:
            result, reasons = "NOT_GREEN", ["NO_GREEN_TAXONOMY_SIGNAL"]
        return GreenRelevanceDecision(
            result,
            positive,
            conditional,
            exclusions,
            {
                "reason_codes": reasons,
                "normalization": "NFKC_CASEFOLD_WHITESPACE_V0.1",
                "matching": "LITERAL_SUBSTRING",
            },
        )
