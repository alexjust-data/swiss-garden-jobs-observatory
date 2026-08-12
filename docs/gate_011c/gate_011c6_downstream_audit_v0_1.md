# GATE-011C-6 downstream audit v0.1

C-6 admitted no new source collection. The correct causal cutoff is therefore
the accepted C-5 cutoff, and all four derived artifacts are exact reuses.

The final Nidwalden correction changed its evidence-supported blocker rationale,
not its terminal state: stable occupation/application identities were proven,
but the mandatory `NW-1616` Praktikum object retains concurrent-cohort identity
ambiguity. No adapter, endpoint, collection evidence or PIT input changed.

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
- new C-6 REVIEW: 0
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
- final blocked/incomplete: 9 / 29
- governed final disposition: 29 / 29
- acquisition coverage: 68.965517%
- readiness: `DAY_0_THRESHOLD_POLICY_PENDING`
- threshold: `PENDING`
- freshness: `PENDING`
- market figure authorized: no

## Decision audit

No C-6 Source reached `ACCEPTED_IMPLEMENTED`, so no new Posting, observation,
green assessment, lifecycle evidence, candidate pair or dedup decision exists.
The 99-review queue is identical to C-5. AUTO_MERGE and cross-source AUTO_MERGE
remain zero; a separate C-6 review audit is not required. Existing critical
green reviews remain non-public and unresolved.

The readiness model's access-review diagnostic continues to reflect frozen
registry authorization fields and is not redefined by this documentation gate.
The scientifically relevant acquisition accounting remains the structurally
complete/healthy `20 / 29` and final blocked `9 / 29` split.

## Exact replay

Dedup reported `idempotent reuse: true`. Premium, Dashboard and Readiness were
then run twice with identical inputs; both passes returned the same IDs and
fingerprints above with `exact_replay_reused=true`. Each input fingerprint maps
to one persisted derived artifact; no duplicate was created.
