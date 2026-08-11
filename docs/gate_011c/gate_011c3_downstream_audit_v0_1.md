# GATE-011C-3 downstream audit v0.1

- `as_of`: `2026-08-11T08:48:00+00:00`
- DedupRun: `5c755ad7-6f36-4685-a47b-aa8613bc11d9`
- PremiumSegmentRun: `6272f371-4444-4506-9b55-97b2d05e4c0a`
- DashboardSnapshot: `3956aa39-f95c-41f9-b8f3-dde8053712bb`
- Day0ReadinessAssessment: `b14b0f96-c14c-4a48-8ffe-7464c43d87fc`

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

## Corrected GR evidence boundary

This replay uses corrected GR run `5f30202b-819f-4d85-a0de-cc6c429d37bb`.
Only `search.html` and `apprentice.html` were requested as vacancy listings;
`stage.html` had zero requests and zero production endpoints. The superseded run
`cebbd705-9cc6-4f40-89a7-aa3b274c7d1a` does not participate.

The replay database was an isolated clone in which the experimental GR observations
and every prior downstream derived artifact were removed before corrected
recollection. The original evidence database was not rewritten. Aggregate totals
remain unchanged because the superseded live `stage.html` request had contributed no
additional unique source ID, not because Schnupperlehre was accepted as Vacancy.

## Exact replay

Immediate identical replay returned the same four IDs and fingerprints with `reused=true` for DedupRun, PremiumSegmentRun, DashboardSnapshot and Day0ReadinessAssessment. No duplicate derived artifact was created.
