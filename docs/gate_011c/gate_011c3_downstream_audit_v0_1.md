# GATE-011C-3 downstream audit v0.1

- `as_of`: `2026-08-11T08:07:00+00:00`
- DedupRun: `579ae68d-6d77-4292-9369-e0f31ee409a0`
- PremiumSegmentRun: `8a646126-52e5-4218-a78e-1189abea808e`
- DashboardSnapshot: `00cd871d-f018-4c6a-a6d1-35356ce1403f`
- Day0ReadinessAssessment: `dfc7a4ea-3259-45e2-b8b3-790b79bd63fd`

## Aligned result

- selected postings: 1,595
- effective vacancies: 1,595
- AUTO_MERGE: 0
- cross-source AUTO_MERGE: 0
- Dedup REVIEW: 98
- pre-existing REVIEW: 98
- new C-3 REVIEW: 0
- critical dedup REVIEW: 0
- noncritical dedup REVIEW: 98
- premium observations: 1,595
- green eligible: 12
- public GREEN_CONFIRMED: 12
- green REVIEW not public / critical green reviews: 44
- mappable: 0
- unmappable public green: 12
- required complete: 14 / 29
- required healthy: 14 / 29
- coverage: 48.275862%
- readiness: `DAY_0_THRESHOLD_POLICY_PENDING`
- threshold: `PENDING`
- freshness: `PENDING`
- market figure authorized: no

## C-3 decision audit

The three implemented sources participated in 195 dedup pair decisions. Outcomes were 0 AUTO_MERGE, 0 REVIEW and 195 KEEP_SEPARATE. Therefore there are no new C-3 AUTO_MERGE or REVIEW rows to enumerate. The existing 98-review queue is unchanged.

## Exact replay

Immediate identical replay returned the same four IDs and fingerprints with `reused=true` for DedupRun, PremiumSegmentRun, DashboardSnapshot and Day0ReadinessAssessment. No duplicate derived artifact was created.
