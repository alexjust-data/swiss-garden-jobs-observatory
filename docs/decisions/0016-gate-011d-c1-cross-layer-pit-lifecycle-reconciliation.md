# ADR 0016 — GATE-011D-C1 cross-layer PIT lifecycle reconciliation

- Status: Accepted for implementation audit
- Date: 2026-08-12
- Baseline: `1a1af1f5ac3fb2657d5b034cd6ff602a5c08cc5b`

## Context

GATE-011E exposed an integration contradiction among closed contracts. GATE-005 makes the first healthy absence `DISAPPEARED_PENDING` and requires a second negative scan at least 48 hours later for `CLOSED_OBSERVED`. GATE-008 retained the last active content observation until PIT evaluation and closed the Vacancy only on `CLOSED_OBSERVED`. GATE-009 removed Premium input at both lifecycle states. GATE-010 correctly required exact Dedup/Premium observation-universe equality. At the incident cutoff this produced 1,971 Dedup observations and 1,889 Premium assessments.

This decision amends GATE-009/010 integration semantics while preserving their scientific purpose. It does not change frozen research, lifecycle rules, dedup behavior, classifier decision tables, or Day-0 policy.

## Decision

Introduce neutral `posting-pit-selection-v0.1`. At cutoff T it selects the latest `ACTIVE` `PostingObservation` as content and the latest `PostingLifecycleEvent` as independent lifecycle evidence.

All lifecycle consumers use the canonical ascending chronology `(observed_at, created_at, pk)` and its exact descending inverse for latest-event selection. `created_at`, not UUID ordering, resolves equal `observed_at` values. Dedup lifecycle status, run-scoped Vacancy state, episode reconstruction, Premium lifecycle evidence, closure and reappearance lookup therefore share one tie-break contract. The tie-break evidence participates in Dedup and Premium input fingerprints.

| Latest lifecycle | Selected content | Economic interpretation |
|---|---|---|
| `NEW` | latest active observation | active |
| `STILL_ACTIVE` | latest active observation | active |
| `DISAPPEARED_PENDING` | previous active observation | pending absence; not closed |
| `CLOSED_OBSERVED` | previous active observation | closed |
| later active/reappearance | new active observation | active; recurrence remains governed by GATE-008 |

A `NOT_FOUND` observation is never classification content. Selecting historical active content does not manufacture active lifecycle state.

Dedup adopts the shared selector without changing `dedup-v0.1`, its fingerprint meaning, weights, thresholds, hard barriers, Vacancy identity, or episode semantics.

Premium keeps `premium-segment-v0.1`, `premium-normalizer-v0.1`, and the existing taxonomy/decision table. Its configuration and fingerprint additionally include `posting-pit-selection-v0.1`; each input fingerprints the selected active observation and latest lifecycle event. Thus a lifecycle transition changes the Premium fingerprint even if content is unchanged.

Dashboard accepts only Premium runs declaring the supported PIT-selection version and still requires exact equality of Dedup selected observation IDs and Premium assessment observation IDs. Historical snapshots remain immutable.

Day-0 distinguishes classifiable evidence from current market membership. The authorized market cohort and authorization-critical green, premium, geospatial, and dedup reviews require an `ACTIVE` run-scoped Vacancy. `CLOSED_OBSERVED` evidence remains auditable but is not current market truth. `DISAPPEARED_PENDING` remains active during the confirmation interval under unchanged GATE-008 semantics.

A pending dedup review is critical when either candidate side is an eligible, run-scoped `ACTIVE` Vacancy whose selected observation is `GREEN_CONFIRMED` or `REVIEW`. This is an effect test, not a both-sides-active test: `KEEP_SEPARATE` preserves current identities, while `MERGE` can reassign membership, recalculate canonical Posting/source precedence, and reconcile lifecycle. A closed-only pair is noncritical. The adversarial matrix establishes that ACTIVE GREEN versus CLOSED GREEN and ACTIVE GREEN versus CLOSED NOT_GREEN are critical; ACTIVE NOT_GREEN versus CLOSED GREEN is noncritical because neither possible outcome supplies an active public market member under the frozen green contract.

## Immutability and compatibility

No observation, lifecycle event, or historical derived artifact is modified. Legacy Premium runs retain their historical meaning but cannot feed a newly corrected Dashboard snapshot. Corrected runs have distinct configuration/fingerprint evidence. Exact replay and concurrency behavior remain governed by the existing run locks and unique fingerprints.

## Migration decision

No migration is required. The correction consists of shared selection code, configuration/fingerprint evidence, compatibility validation, regressions, and documentation. Experimental 011E migrations are not dependencies and are not imported.

## Live acceptance

At `2026-08-12T10:20:02.339073Z`, corrected Dedup and Premium each select exactly 1,971 observations; both exact set differences are zero. Dashboard snapshot `048dedf2-bc1b-4191-8f1c-08cf768fdf2a` builds successfully. Readiness assessment `9c0e6f80-e5d6-4026-8ecd-1e591be0e74f` remains unauthorized (`DAY_0_BLOCKED_BY_DATA_QUALITY`), as expected, because this gate performs no review adjudication or policy change.

## Preserved contracts

- GATE-005 two-negative/48-hour closure confirmation;
- `dedup-v0.1` and GATE-008 recurrence;
- green and Premium decision tables;
- GATE-010 exact universe equality and immutable PIT artifacts;
- GATE-011D coverage, freshness, eligible-source, and review policy;
- all C-6 source dispositions, geography, access governance, and Job-Room isolation.

GATE-011E remains suspended. After this correction is independently audited and merged, it must restart from a fresh branch; its experimental code and migrations are not authoritative.
