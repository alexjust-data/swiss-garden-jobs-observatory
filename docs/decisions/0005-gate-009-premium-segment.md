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

## Independent audit correction

The final GATE-009 audit replaced substring matching with boundary-aware token-sequence matching over visible text. HTML attributes, scripts, styles, templates, and URLs are not authorized classification surfaces. Scope dispatch is explicit for every frozen `evidence_scope`; GATE-009 has no source-profile evidence object, so `JOB_OR_SOURCE` evaluates job evidence only and source-profile support fails closed. Source names remain non-evidence.

Employer-profile records are cumulative immutable assertions. They apply only when both their `Source` and explicit `employer_identity_key` match source evidence carried by the observation, and the observed employer label matches under the conservative normalizer. Every applicable assertion is fingerprinted and linked to the assessment. There is no fuzzy employer resolution or implicit supersession.

Runs classify the effective lifecycle-active source observation at `as_of`. Immutable `NEW`/`STILL_ACTIVE` lifecycle evidence admits a posting; `DISAPPEARED_PENDING` and `CLOSED_OBSERVED` exclude it. Legacy observations without lifecycle events retain a conservative ACTIVE-observation fallback because GATE-005 intentionally did not fabricate historical events. Green admission is restricted to `green-relevance-v0.1` and `research-v0.4` evidence available at `as_of`.

The frozen PostingObservation v1.2 JSON Schema is revalidated and linked provenance must agree with the model and RAW SHA-256 before classification. Exact-run creation is serialized by a PostgreSQL transaction advisory lock. A failure rolls back the run and every assessment; `FAILED` is reserved and intentionally not persisted because GATE-009 uses all-or-nothing transactions rather than partial workflow state.

`PremiumSegmentRun` and its assessments remain the sole historical result; no mutable operational projection exists. Database and application constraints enforce run completeness, hash formats, ordered timestamps, status/segment compatibility, protected private-segment context, cross-observation green identity, review eligibility, and materially unique employer evidence. Premium and private-residential classifications use protected `PRIVATE_RESIDENCE` context; future presentation layers must never treat a segment as permission to expose exact coordinates or addresses.