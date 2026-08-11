# GATE-011C-5 downstream audit v0.1

- `as_of`: `2026-08-11T19:18:11.999868+00:00`
- DedupRun: `0529ad0c-ac03-41e6-a14c-035125ab3f2b`
- Dedup fingerprint: `51f96a3caa202d141fada638fa0ad6b2e7b126482bbfa1cc0aed941d866fa0b5`
- PremiumSegmentRun: `227b2e1a-629e-4655-9b71-10b4acad835f`
- Premium fingerprint: `3e98750ee0636d75b7b62744d8b46221d2eea0185db9652e7f07866f644cadc0`
- DashboardSnapshot: `b08dfb21-438b-4dfc-bdd1-feb7b725fe4d`
- Dashboard fingerprint: `95ee4dd0b3fdffdd9c760155a81205863997a956c3e1008a966d68b3cc11f79d`
- Day0ReadinessAssessment: `315c5df9-fb0a-4433-8072-81a40d20c7be`
- Readiness fingerprint: `9ed0c378c99ddb62c04290d67bcc12fe80cacb51127a53851900729a98e7c19f`

## Aligned result

- selected postings: 1,867
- effective vacancies: 1,867
- AUTO_MERGE: 0
- cross-source AUTO_MERGE: 0
- Dedup REVIEW: 99
- pre-existing REVIEW: 99
- new C-5 REVIEW: 0
- critical dedup REVIEW: 0
- noncritical dedup REVIEW: 99
- premium observations: 1,867
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

The C-4 queue contained 99 unresolved dedup reviews and the corrected aligned
C-5 run contains the same 99. The added GL court Praktikum produced one new
Vacancy and no candidate REVIEW/AUTO_MERGE decision. C-5 therefore introduced
no new dedup REVIEW and no AUTO_MERGE; a separate C-5 dedup-review artifact is
not required. Existing SG pair `6421 / 6422` remains unresolved. The two
additional critical green reviews are classifier outcomes from GL and Stadt
St. Gallen, not dedup decisions, and remain non-public under the existing
Day-0 contract.

## Exact replay

Immediate identical replay returned the same four IDs and fingerprints shown
above. Dedup, Premium, Dashboard and Readiness each reported
`exact_replay_reused=true`. Each input fingerprint maps to exactly one
persisted derived artifact; no duplicate artifact was created.
