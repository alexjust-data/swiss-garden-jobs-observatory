# ADR 0018 — GATE-011F required-source recovery

## Decision

Starting from merged GATE-011E baseline
`cbf1054b329843ea3fff7eeac77ea9342df60147`, all nine C-6 blocked
required Sources were independently tested against the recovery contract frozen
before current-state evaluation. Zero Sources met their condition.

Consequently:

- there is no `ACCEPTED_BLOCKED -> ACCEPTED_IMPLEMENTED` transition;
- the historical C-6 disposition and `day0-authorization-v0.1` configuration remain
  unchanged and continue to replay exactly;
- no speculative source-disposition model or empty transition set is introduced;
- no adapter, endpoint, source identity, classifier, dedup or policy semantics change;
- all 20 implemented required Sources were refreshed in one contemporary cycle;
- Day-0 remains not authorized.

## Per-source decisions

AI, BE, FR, JU, NW, OW, UR and VS remain blocked for their C-6 primary
reason. AG shows official platform/access presentation drift, but still lacks a
deterministic complete acquisition contract; its outcome is
`SOURCE_CONTRACT_DRIFT`, not recovery. Detailed official evidence and hashes are in
`docs/day0/gate_011f_blocked_source_recovery_audit_v0_1.md`.

Uri was the only plausible technical candidate. Its official listing and sample
details sometimes returned quickly, but a repeated official request timed out.
That failed the predeclared reproducibility condition before two consecutive
FULL_SOURCE runs. Implementing after only the successful response would fit the
contract to the outcome.

## Contemporary refresh and PIT result

All 20 existing implementations completed with `SUCCEEDED`, `HEALTHY`,
`snapshot_complete=true`, and equal listing/detail/observation/green counters.
No blocked Source was requested.

At `2026-08-12T20:34:34.288688Z`:

- DedupRun `561c5f7c-3242-4161-b387-7b460a5ca00d`, 2,000 observations,
  1,999 effective active Vacancies;
- PremiumSegmentRun `861b8c04-ecaf-40be-b57c-e058dea5392a`;
- DashboardSnapshot `dc817be3-4250-46e2-b7a1-784f08722f8c`;
- Day0ReadinessAssessment `abdc4afb-8cff-44f3-8b8b-3054df09cccd`;
- eligibility 20/29, active eligible GREEN_CONFIRMED 14;
- 54 critical green and one critical dedup review;
- `DAY_0_NOT_AUTHORIZED`.

Exact replay reused all four fingerprints. The refresh created new observations, so
the two prior `INSUFFICIENT_EVIDENCE` decisions were neither overwritten nor
reused for different assessments.

## Preserved governance

`day0-coverage-v0.1`, `full-source-freshness-v0.1`, the 29-Source
denominator, C-6 evidence, GATE-011E review decisions, `dedup-v0.1`,
`green-relevance-v0.1`, `premium-segment-v0.1`, geography, and inactive
Job-Room remain unchanged. Frozen research has zero changes.

