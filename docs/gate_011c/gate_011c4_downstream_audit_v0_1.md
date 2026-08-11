# GATE-011C-4 downstream audit v0.1

- `as_of`: `2026-08-11T10:29:52.764976+00:00`
- DedupRun: `2e7b1110-3f3e-41b0-9d9a-e35491f9289f`
- PremiumSegmentRun: `85d4e907-311a-4de0-93eb-64f1c03a68a7`
- DashboardSnapshot: `6163b449-cb45-4cd6-808e-e2e842be453f`
- Day0ReadinessAssessment: `894e4f64-db47-4c9b-9f3b-d8d1d9c6b532`

## Aligned result

- selected postings: 1,753
- effective vacancies: 1,753
- AUTO_MERGE: 0
- cross-source AUTO_MERGE: 0
- Dedup REVIEW: 99
- pre-existing REVIEW: 98
- new C-4 REVIEW: 1
- critical dedup REVIEW: 0
- noncritical dedup REVIEW: 99
- premium observations: 1,753
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

The three newly implemented sources participated in 89 dedup pair decisions: 88 `KEEP_SEPARATE`, one `REVIEW` and zero `AUTO_MERGE`. The only new review is committed separately in `gate_011c4_dedup_review_audit_v0_1.md` and remains unresolved.

## Exact replay

Immediate identical replay returned the same four IDs and fingerprints. Dedup, Premium, Dashboard and Readiness each reported `exact_replay_reused=true` (the dedup command reports `idempotent reuse: true`). No duplicate derived artifact was created.
