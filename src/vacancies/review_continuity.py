from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q

from .evidence import (
    DEDUP_REVIEW_MATERIAL_VERSION,
    PostingEvidence,
    dedup_review_material_fingerprint,
    select_posting_evidence,
)
from .models import DedupDecision, DedupReviewDecisionApplication
from .normalizer import (
    DEDUP_VERSION,
    NORMALIZER_VERSION,
    REPOST_WINDOW_DAYS,
    SOURCE_PRECEDENCE_VERSION,
)
from .scoring import WEIGHTS

APPLICATION_METHOD = "MATERIAL_IDENTICAL_HUMAN_REUSE"
_SHA256 = re.compile(r"[0-9a-f]{64}")
FROZEN_CONFIGURATION: dict[str, Any] = {
    "weights": {key: str(value) for key, value in WEIGHTS.items()},
    "thresholds": {"auto_merge": "0.90", "review": "0.78"},
    "repost_window_days": REPOST_WINDOW_DAYS,
    "normalizer_version": NORMALIZER_VERSION,
    "source_precedence_version": SOURCE_PRECEDENCE_VERSION,
    "review_material_version": DEDUP_REVIEW_MATERIAL_VERSION,
}


class DedupContinuityValidationError(ValueError):
    pass


class UnverifiableLegacyHumanDecisionError(DedupContinuityValidationError):
    pass


@dataclass(frozen=True)
class DedupMaterialProof:
    algorithm_decision: DedupDecision
    left: PostingEvidence
    right: PostingEvidence
    material_fingerprint: str

    @property
    def pair(self) -> frozenset[str]:
        return frozenset((self.left.posting_id, self.right.posting_id))


def reconstruct_algorithm_material(
    algorithm: DedupDecision, configuration: dict[str, Any]
) -> DedupMaterialProof:
    if algorithm.method == DedupDecision.Method.HUMAN:
        raise DedupContinuityValidationError("algorithm decision cannot be HUMAN")
    if algorithm.dedup_version != DEDUP_VERSION:
        raise DedupContinuityValidationError("dedup version is incompatible")
    if algorithm.normalizer_version != NORMALIZER_VERSION:
        raise DedupContinuityValidationError("normalizer version is incompatible")
    selected = {
        item.posting_id: item for item in select_posting_evidence(algorithm.dedup_run.as_of)
    }
    try:
        left = selected[str(algorithm.posting_a.pk)]
        right = selected[str(algorithm.posting_b.pk)]
    except KeyError as exc:
        raise UnverifiableLegacyHumanDecisionError(
            "UNVERIFIABLE_LEGACY_HUMAN_DECISION: historical PostingEvidence is absent"
        ) from exc
    if {left.observation_id, right.observation_id} != {
        str(algorithm.observation_a.pk),
        str(algorithm.observation_b.pk),
    }:
        raise UnverifiableLegacyHumanDecisionError(
            "UNVERIFIABLE_LEGACY_HUMAN_DECISION: historical observation selection differs"
        )
    material = dedup_review_material_fingerprint(
        left,
        right,
        configuration,
        method=algorithm.method,
        score=str(algorithm.score),
        feature_scores=algorithm.feature_scores,
        hard_keys=algorithm.blocking_evidence.get("hard_keys", []),
        hard_barriers=algorithm.hard_barriers,
        algorithm_outcome=algorithm.outcome,
    )
    return DedupMaterialProof(algorithm, left, right, material)


def reconstruct_source_human_material(
    source: DedupDecision, configuration: dict[str, Any]
) -> DedupMaterialProof:
    if source.method != DedupDecision.Method.HUMAN:
        raise DedupContinuityValidationError("source decision is not HUMAN")
    if source.outcome not in {
        DedupDecision.Outcome.MERGE,
        DedupDecision.Outcome.KEEP_SEPARATE,
    }:
        raise DedupContinuityValidationError("source human outcome is not reusable")
    if source.dedup_version != DEDUP_VERSION or source.normalizer_version != NORMALIZER_VERSION:
        raise DedupContinuityValidationError("source versions are incompatible")
    algorithm_id = source.evidence.get("algorithm_decision_id")
    if not isinstance(algorithm_id, str) or not algorithm_id:
        raise UnverifiableLegacyHumanDecisionError(
            "UNVERIFIABLE_LEGACY_HUMAN_DECISION: algorithm_decision_id is absent"
        )
    try:
        algorithm = DedupDecision.objects.select_related("dedup_run").get(pk=algorithm_id)
    except (DedupDecision.DoesNotExist, ValueError) as exc:
        raise UnverifiableLegacyHumanDecisionError(
            "UNVERIFIABLE_LEGACY_HUMAN_DECISION: source algorithm decision is unavailable"
        ) from exc
    if algorithm.dedup_run.pk != source.dedup_run.pk:
        raise DedupContinuityValidationError("source algorithm belongs to another DedupRun")
    if frozenset(map(str, (algorithm.posting_a.pk, algorithm.posting_b.pk))) != frozenset(
        map(str, (source.posting_a.pk, source.posting_b.pk))
    ):
        raise DedupContinuityValidationError("source algorithm belongs to another Posting pair")
    if algorithm.created_at > source.created_at:
        raise DedupContinuityValidationError("source human decision predates its algorithm")
    proof = reconstruct_algorithm_material(algorithm, configuration)
    stored = source.evidence.get("material_fingerprint")
    if stored is not None and stored != proof.material_fingerprint:
        raise DedupContinuityValidationError("stored source material fingerprint is false")
    stored_version = source.evidence.get("material_version")
    if stored_version is not None and stored_version != DEDUP_REVIEW_MATERIAL_VERSION:
        raise DedupContinuityValidationError("stored source material version is incompatible")
    return proof


def validate_dedup_review_application(
    application: DedupReviewDecisionApplication,
    configuration: dict[str, Any],
    *,
    as_of: datetime | None = None,
) -> tuple[DedupMaterialProof, DedupMaterialProof]:
    source = application.source_human_decision
    target = application.target_algorithm_decision
    errors: list[str] = []
    if application.application_method != APPLICATION_METHOD:
        errors.append("application method is invalid")
    if application.fingerprint_version != DEDUP_REVIEW_MATERIAL_VERSION:
        errors.append("fingerprint version is invalid")
    if not _SHA256.fullmatch(application.material_fingerprint):
        errors.append("material fingerprint is not lower-case SHA-256")
    if frozenset(map(str, (source.posting_a.pk, source.posting_b.pk))) != frozenset(
        map(str, (target.posting_a.pk, target.posting_b.pk))
    ):
        errors.append(
            "source and target Posting pairs differ: "
            f"source={source.posting_a.pk}/{source.posting_b.pk} "
            f"target={target.posting_a.pk}/{target.posting_b.pk}"
        )
    if source.dedup_version != target.dedup_version:
        errors.append("source and target dedup versions differ")
    if application.evidence.get("source_decision_id") != str(source.pk):
        errors.append("source_decision_id provenance differs")
    if application.evidence.get("target_decision_id") != str(target.pk):
        errors.append("target_decision_id provenance differs")
    if source.created_at > application.created_at:
        errors.append("application predates source human authority")
    if target.created_at > application.created_at:
        errors.append("application predates target algorithm evidence")
    if as_of is not None and (
        source.created_at > as_of or target.created_at > as_of or application.created_at > as_of
    ):
        errors.append("application authority is not causally available")
    direct = DedupDecision.objects.filter(
        dedup_run=target.dedup_run,
        method=DedupDecision.Method.HUMAN,
    ).filter(
        Q(evidence__algorithm_decision_id=str(target.pk))
        | (
            Q(posting_a=target.posting_a)
            & Q(posting_b=target.posting_b)
            & Q(created_at__gte=target.created_at)
        )
    )
    if direct.exists():
        errors.append("target has conflicting direct human authority")
    if errors:
        raise DedupContinuityValidationError("; ".join(errors))
    source_proof = reconstruct_source_human_material(source, configuration)
    target_proof = reconstruct_algorithm_material(target, configuration)
    if source_proof.pair != target_proof.pair:
        raise DedupContinuityValidationError("reconstructed Posting pairs differ")
    if not (
        source_proof.material_fingerprint
        == target_proof.material_fingerprint
        == application.material_fingerprint
    ):
        raise DedupContinuityValidationError("source/target/stored material fingerprints differ")
    return source_proof, target_proof


def _same_application(
    application: DedupReviewDecisionApplication,
    source: DedupDecision,
    material: str,
) -> bool:
    return (
        application.source_human_decision.pk == source.pk
        and application.material_fingerprint == material
        and application.fingerprint_version == DEDUP_REVIEW_MATERIAL_VERSION
        and application.application_method == APPLICATION_METHOD
    )


def create_dedup_review_application(
    *,
    target_algorithm_decision: DedupDecision,
    source_human_decision: DedupDecision,
    configuration: dict[str, Any],
) -> tuple[DedupReviewDecisionApplication, bool]:
    source_proof = reconstruct_source_human_material(source_human_decision, configuration)
    target_proof = reconstruct_algorithm_material(target_algorithm_decision, configuration)
    if source_proof.pair != target_proof.pair:
        raise DedupContinuityValidationError("source decision belongs to another Posting pair")
    if source_proof.material_fingerprint != target_proof.material_fingerprint:
        raise DedupContinuityValidationError("source decision material differs")
    existing = DedupReviewDecisionApplication.objects.filter(
        target_algorithm_decision=target_algorithm_decision
    ).first()
    if existing is not None:
        validate_dedup_review_application(existing, configuration)
        if _same_application(existing, source_human_decision, target_proof.material_fingerprint):
            return existing, False
        raise DedupContinuityValidationError("conflicting dedup continuity authority")
    evidence = {
        "source_decision_id": str(source_human_decision.pk),
        "target_decision_id": str(target_algorithm_decision.pk),
        "source_algorithm_decision_id": str(source_proof.algorithm_decision.pk),
        "source_dedup_run_id": str(source_proof.algorithm_decision.dedup_run.pk),
        "source_as_of": source_proof.algorithm_decision.dedup_run.as_of.isoformat(),
        "source_material_fingerprint": source_proof.material_fingerprint,
        "target_dedup_run_id": str(target_algorithm_decision.dedup_run.pk),
        "target_as_of": target_algorithm_decision.dedup_run.as_of.isoformat(),
        "target_material_fingerprint": target_proof.material_fingerprint,
    }
    application = DedupReviewDecisionApplication(
        target_algorithm_decision=target_algorithm_decision,
        source_human_decision=source_human_decision,
        material_fingerprint=target_proof.material_fingerprint,
        fingerprint_version=DEDUP_REVIEW_MATERIAL_VERSION,
        application_method=APPLICATION_METHOD,
        evidence=evidence,
    )
    try:
        with transaction.atomic():
            application.save()
    except IntegrityError as exc:
        concurrent = DedupReviewDecisionApplication.objects.filter(
            target_algorithm_decision=target_algorithm_decision
        ).first()
        if concurrent is not None:
            validate_dedup_review_application(concurrent, configuration)
            if _same_application(
                concurrent, source_human_decision, target_proof.material_fingerprint
            ):
                return concurrent, False
        raise DedupContinuityValidationError(
            "conflicting concurrent dedup continuity authority"
        ) from exc
    validate_dedup_review_application(application, configuration)
    return application, True
