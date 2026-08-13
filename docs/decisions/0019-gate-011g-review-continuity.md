# ADR 0019: governed review continuity across refreshes

Status: Accepted for GATE-011G audit

Date: 2026-08-13

Baseline: merged GATE-011F `0d0acd753b42d004d3243866d4daf7449dafebe8`

## Context

GATE-011E left 51 active green vacancies, two critical green reviews, and zero critical dedup reviews. A normal GATE-011F refresh replaced observations and assessments, reducing effective green vacancies to 14 while reopening 54 critical green reviews and one critical dedup review. The classifier and human decisions were correct; the architecture had no governed way to apply human knowledge to later materially identical evidence.

The material contract was frozen at `docs/day0/gate_011g_review_continuity_contract_v0_1.md` in the independent contract-only commit `3c5824e0183e151bc0437fd968a926d93264609e`, before lineage measurement. The measured evidence is recorded in `docs/day0/gate_011g_review_lineage_audit_v0_1.md`; operational evidence is in `docs/day0/gate_011g_operational_acceptance_v0_1.md`.

## Decision

Keep immutable assessments and exact human decisions separate from append-only reuse applications. A reuse application is inherited knowledge, never a newly manufactured human review.

Green reuse uses `green-review-material-v0.1`. Its identity boundary is exact Source plus governed Posting and source-native ID. Its SHA-256 fingerprint covers frozen classifier, taxonomy/hash and governance versions; normalized TITLE, classifier TEXT concatenation and ORGANIZATION surfaces; original result; all positive, conditional and exclusion evidence; and reason codes. RAW hashes remain pinned provenance but are not material equality, allowing byte-level transport changes without erasing semantically identical human knowledge.

Dedup reuse uses `dedup-review-material-v0.1` over the same canonically ordered Posting pair. It binds dedup/normalizer/config versions, identity surfaces, requisition and redirect evidence, scores, keys, hard barriers, algorithm outcome, and lifecycle material. Routine `STILL_ACTIVE` in the same active episode is non-material. Closure, reappearance, episode/repost consequences, identity inputs, pair, or version changes invalidate reuse.

For both families, every target, source decision, and application must be causally available by cutoff. Direct and inherited authority cannot conflict. Premium pins whether green authority is classifier, direct human decision, or material-identical human reuse, including the exact evidence IDs in its fingerprint.

## Evidence and consequences

At the GATE-011F cutoff all 54 critical green reviews materially matched prior human evidence: 37 confirmed-green, 15 confirmed-not-green and two insufficient decisions. The one critical dedup pair materially matched a prior `KEEP_SEPARATE`. Same-cutoff reconstruction therefore restored 51 active green vacancies while correctly retaining two green reviews and no critical dedup review.

The second governed 20-Source refresh selected 2,002 observations. It again produced 54 green review assessments, all material matches with the same 37/15/2 outcomes and no invalidations or cross-identity reuse. Dedup produced 103 algorithm review candidates: the governed prior pair reused `KEEP_SEPARATE`; 102 new pairs remained noncritical and unresolved.

The final aligned cutoff is `2026-08-13T06:34:17.993915Z`. PIT IDs and fingerprints are:

| Artifact | ID | Fingerprint |
|---|---|---|
| DedupRun | `2df4e227-dbbb-477d-a47e-aafdc1567ff3` | `435fae525f1cf0185c6e1687bb067cdfa1350dc58eae1fff8bec1c408fe335f2` |
| PremiumSegmentRun | `971bb3ab-d300-4525-8862-434346fe2563` | `a5126bad31a856b136a38bedeaeed5acd2c4e6b09a3eda31db58d542f4e33ec7` |
| DashboardSnapshot | `f9e84544-19b6-4741-bc5e-c0ec167c9ed6` | `5e0ffe8ff550be3376f01cbadc9a6376a2b5f769214e91f437df5e39a4c230b2` |
| Day0ReadinessAssessment | `5d33f761-5c81-473c-8f35-f806d204f6b0` | `e36dd4e628997ca5e4265f2830ba12fe4118e82f9ce2b26590eaf4abcd49dd72` |

Exact replay returned all four IDs/fingerprints and reused each artifact; continuity created zero duplicates. Day-0 remains `DAY_0_BLOCKED_BY_DATA_QUALITY`: only 20 of 29 required Sources are eligible versus the frozen minimum of 24, and the two inherited-insufficient reviews remain critical. The headline remains null. No blocked Source was requested and no closed classifier, scoring, premium, coverage, freshness, authorization, source-disposition, geography, or Job-Room contract changed.

## Independent-audit enforcement correction

Audit of head `eb3476b2d5174a279877f7d46302395cb66888f2` identified enforcement gaps, not a material-contract defect. Legacy dedup reuse now reconstructs source material from the exact historical algorithm decision and cutoff; missing evidence is `UNVERIFIABLE_LEGACY_HUMAN_DECISION`. Dedup applications have one central create/verify path and are revalidated by the engine. Dedup and green both enforce direct authority XOR inherited authority. Green creation reconciles identical concurrent collisions and rejects ambiguous prior knowledge.

The real legacy bridge reconstructs equal source and target fingerprint `c9f0c0f6a4c0d57062bd15b8024dd434bee2d889a531b74d950277e77d518087`. The corrected aligned cutoff `2026-08-13T07:52:00Z` produced Dedup `d5a44c47-e495-4a0b-b419-824fbba94606`, Premium `3c522be5-464d-4b4c-abc4-87bb90bdda33`, Dashboard `23ae1e19-9dc4-4e58-9e9a-7fa28c0dfcc8` and Readiness `d0500be7-96a6-450a-8089-26ef0ef8a0ae`. Exact replay and one-artifact-per-fingerprint passed; the 37/15/2 lineage and Day-0 consequence are unchanged because the evidence reproduced them.
