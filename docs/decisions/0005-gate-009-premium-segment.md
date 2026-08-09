# Decision 0005: GATE-009 Premium Segment

## Status

Accepted for implementation in GATE-009.

## Decision

Premium/private-segment classification is a deterministic, versioned derived layer above immutable `PostingObservation` and `GreenRelevanceAssessment` evidence. It does not read the mutable Vacancy projection and does not alter collection, lifecycle, geospatial, green-relevance, or deduplication state.

`PremiumSegmentRun` and `PremiumSegmentAssessment` are immutable and run-scoped. They are the authoritative PIT result. GATE-009 intentionally adds no mutable operational projection; therefore a historical run cannot roll back a newer result.

The classifier uses `premium-segment-v0.1`, `premium-normalizer-v0.1`, taxonomy version `research-v0.4`, and the exact SHA-256 of the frozen 26-row CSV. Matching is Unicode NFKC, casefolded, punctuation/whitespace controlled, literal, and evidence-scope constrained. No ML, LLM, embeddings, fuzzy matching, external enrichment, geographic wealth inference, or source-name inference is used.

Assessment status is separate from market segment. `REVIEW` is never a segment. Base weights are retained as evidence metadata and are not interpreted as probabilities or blindly summed. Confidence is categorical evidence strength (`STRONG`, `MODERATE`, `WEAK`, `NONE`).

Employer-profile support requires explicit append-only `EmployerProfileEvidence` with provenance and `available_at`; employer names alone are never evidence. Exact private addresses remain only in authorized immutable source evidence and are not copied into assessment evidence, review evidence, logs, or command output. Estate classification records `PRIVATE_RESIDENCE` under privacy policy `location-privacy-v0.1`.

`Privatgarten` and generic private-household evidence can support `PRIVATE_RESIDENTIAL_STANDARD`, never premium by themselves. Auxiliary design and household-requirement signals are insufficient alone. Municipality wealth and property values are prohibited inference only.

The frozen `docs/research/v0_4/` package remains authoritative, read-only, and unchanged. GATE-008 is frozen and its thresholds, weights, identities, episodes, PIT projection, and six unresolved live reviews are outside GATE-009.
