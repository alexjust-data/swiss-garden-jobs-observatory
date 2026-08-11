# GATE-011C-4 downstream audit v0.1

- `as_of`: `2026-08-11T15:02:39.985730+00:00`
- DedupRun: `ca0153ee-e80d-4c76-8bd7-055b392a2fd3`
- PremiumSegmentRun: `31cd6cbc-5424-4b30-9420-3513904b8f7f`
- DashboardSnapshot: `c203e85d-309c-4ac6-83cb-c2e29caf06fd`
- Day0ReadinessAssessment: `08517161-daa0-4053-bb5b-1d7b4e68e675`

## Aligned result

- selected postings: 1,783
- effective vacancies: 1,783
- AUTO_MERGE: 0
- cross-source AUTO_MERGE: 0
- Dedup REVIEW: 99
- pre-existing REVIEW: 98
- new C-4 REVIEW: 1
- critical dedup REVIEW: 0
- noncritical dedup REVIEW: 99
- premium observations: 1,783
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

The three newly implemented sources participated in 432 dedup pair decisions: 431
`KEEP_SEPARATE`, one `REVIEW` and zero `AUTO_MERGE`. LU participated in 354
decisions; every one is `KEEP_SEPARATE`, so the corrected apprenticeship surface
created no REVIEW or AUTO_MERGE. The only new C-4 review remains SG pair
`6421 / 6422`, committed separately in
`gate_011c4_dedup_review_audit_v0_1.md` and unresolved.

## Exact replay

Immediate identical replay returned the same four IDs and fingerprints. Dedup, Premium,
Dashboard and Readiness each reported `exact_replay_reused=true` (the dedup command
reports `idempotent reuse: true`). Each input fingerprint has exactly one persisted
artifact. No duplicate derived artifact was created.
