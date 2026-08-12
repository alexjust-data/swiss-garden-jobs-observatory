# ADR 0017 — GATE-011E Day-0 operational recovery

Status: proposed in draft PR. Baseline: `a410a1d62ccbefb7157803045142c3b95b651c94` (merged GATE-011D-C1).

## Decision

GATE-011E preserves `day0-coverage-v0.1`, `full-source-freshness-v0.1` and `day0-authorization-v0.1`. It refreshes exactly the 20 C-6 `ACCEPTED_IMPLEMENTED` required Sources, reconstructs the eligible cohort, and resolves only reviews capable of changing that cohort.

Green review adjudication is new immutable PIT evidence. `GreenRelevanceReviewDecision` is append-only, time-scoped and versioned as `green-review-v0.1`. One assessment has at most one decision per governance version; exact retries reuse it, while conflicts fail closed and require a future review-policy version. Each decision must pin bounded source surfaces, observation/assessment/Source/native IDs, raw SHA-256, the original REVIEW state and an evidence basis. It never overwrites `green-relevance-v0.1`. Premium persists the effective green result and exact review-decision ID and fingerprints both; Dashboard and Day-0 consume that pinned result. Decisions after a cutoff cannot change historical runs.

Two freshly generated migrations are required: observations `0010` creates immutable human green decisions; premium `0002` pins effective green evidence and backfills historical rows from their original immutable classifier assessment. They were generated from corrected main and do not import the suspended experimental 011E migration chain.

## Operational and review results

All 20 refresh runs were successful, healthy, complete and fresh; none of the nine blocked Sources was requested. The critical queue moved from 55 green plus one dedup to two unresolved green items and zero dedup. Thirty-seven green reviews were confirmed green, 16 confirmed not green, two retained insufficient evidence. The distinct Brugg and Emmen federal postings were kept separate.

PIT sequencing preserves a post-refresh pre-review assessment and uses a later post-review cutoff. The final aligned/replayable IDs and fingerprints are recorded in `docs/day0/day0_authorization_gap_v0_1.md`.

## Authorization consequence

The final eligible cohort is 20/29. Operational source recovery is complete, but the coverage deficit is four Sources and two quality reviews remain. Day-0 is not authorized. A future source-recovery gate must recover at least four blocked required Sources before coverage can pass; this ADR neither weakens the threshold nor reopens C-6 dispositions.
