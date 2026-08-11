# GATE-011C-4 downstream audit v0.1

- `as_of`: `2026-08-11T11:26:56.508608+00:00`
- DedupRun: `6f885419-3294-4bcb-a7a3-08a978f455ea`
- PremiumSegmentRun: `46082f75-c4c3-47db-a2c7-d2b5203143ed`
- DashboardSnapshot: `1dcacbf8-f012-49ce-bef6-6d102eed9b13`
- Day0ReadinessAssessment: `7fe25fee-0a41-4eda-bef5-494e1815f3da`

## Aligned result

- selected postings: 1,782
- effective vacancies: 1,782
- AUTO_MERGE: 0
- cross-source AUTO_MERGE: 0
- Dedup REVIEW: 99
- pre-existing REVIEW: 98
- new C-4 REVIEW: 1
- critical dedup REVIEW: 0
- noncritical dedup REVIEW: 99
- premium observations: 1,782
- green eligible: 12
- public GREEN_CONFIRMED: 12
- green REVIEW not public / critical green reviews: 51
- mappable: 0
- unmappable public green: 12
- required complete: 17 / 29
- required healthy: 17 / 29
- required blocked: 12
- coverage: 58.620690%
- readiness: `DAY_0_THRESHOLD_POLICY_PENDING`
- threshold: `PENDING`
- freshness: `PENDING`
- market figure authorized: no

## C-4 decision audit

The three newly implemented sources participated in 431 dedup pair decisions: 430
`KEEP_SEPARATE`, one `REVIEW` and zero `AUTO_MERGE`. LU participated in 353
decisions; every one is `KEEP_SEPARATE`, so the corrected apprenticeship surface
created no REVIEW or AUTO_MERGE. The only new C-4 review remains SG pair
`6421 / 6422`, committed separately in
`gate_011c4_dedup_review_audit_v0_1.md` and unresolved.

## Exact replay

Immediate identical replay returned the same four IDs and fingerprints. Dedup, Premium,
Dashboard and Readiness each reported `exact_replay_reused=true` (the dedup command
reports `idempotent reuse: true`). Each input fingerprint has exactly one persisted
artifact. No duplicate derived artifact was created.
