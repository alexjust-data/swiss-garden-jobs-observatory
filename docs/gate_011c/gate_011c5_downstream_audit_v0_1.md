# GATE-011C-5 downstream audit v0.1

- `as_of`: `2026-08-11T16:39:46.055808+00:00`
- DedupRun: `0bdea7b5-23be-4659-83a5-4f8349d624a3`
- Dedup fingerprint: `76c6343ee26515a3cceed0a9bd50be542b865eeea7e0d990fd7346f78497e356`
- PremiumSegmentRun: `e5c36210-0adc-4032-af7a-b4474f32dc02`
- Premium fingerprint: `7e94da3a2544831e8ce6d2d55eda705298ceff5ec42b827bf64ba362c38ab378`
- DashboardSnapshot: `43fbaef0-d2d6-4b84-8792-ccf12fb9a581`
- Dashboard fingerprint: `a70098db0481f78e69a969659a6fb37d0db2c0abd1a51191e66148405dbdb6d1`
- Day0ReadinessAssessment: `3525fdb1-3f16-41c2-b444-6b11f4f39b6e`
- Readiness fingerprint: `9b3616400240d1bbcadda55eb29110030548f046db7f8d609c6844c14ec6d4cb`

## Aligned result

- selected postings: 1,866
- effective vacancies: 1,866
- AUTO_MERGE: 0
- cross-source AUTO_MERGE: 0
- Dedup REVIEW: 99
- pre-existing REVIEW: 99
- new C-5 REVIEW: 0
- critical dedup REVIEW: 0
- noncritical dedup REVIEW: 99
- premium observations: 1,866
- green eligible: 14
- public GREEN_CONFIRMED: 14
- green REVIEW not public / critical green reviews: 53
- mappable: 0
- unmappable public green: 14
- required complete: 20 / 29
- required healthy: 20 / 29
- required blocked/incomplete: 9
- coverage: 68.965517%
- readiness: `DAY_0_THRESHOLD_POLICY_PENDING`
- threshold: `PENDING`
- freshness: `PENDING`
- market figure authorized: no

## C-5 decision audit

The C-4 queue contained 99 unresolved dedup reviews and the aligned C-5 run
contains the same 99. C-5 therefore introduced no new dedup REVIEW and no
AUTO_MERGE; a separate C-5 dedup-review artifact is not required. Existing SG
pair `6421 / 6422` remains unresolved. The two additional critical green
reviews are classifier outcomes from GL and Stadt St. Gallen, not dedup
decisions, and remain non-public under the existing Day-0 contract.

## Exact replay

Immediate identical replay returned the same four IDs and fingerprints shown
above. Dedup, Premium, Dashboard and Readiness each reported
`exact_replay_reused=true`. Each input fingerprint maps to exactly one
persisted derived artifact; no duplicate artifact was created.
