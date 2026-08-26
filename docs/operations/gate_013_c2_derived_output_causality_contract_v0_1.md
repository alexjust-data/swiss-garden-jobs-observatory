# GATE-013-C2 — Derived-output causality contract v0.1

Status: `FROZEN_FOR_IMPLEMENTATION`

- baseline: merged `main` at `d1243436915dfde055a7482898509d2a55bb727d`;
- prior cycle authority: `daily-observatory-cycle-v0.3`;
- corrected cycle authority: `daily-observatory-cycle-v0.4`;
- scope: daily Dedup-continuity output causality only.

## 1. Incident and purpose

The first real geospatial-v0.2 production acceptance created the governed 51-row resolution set and
proved exact no-provider replay. While constructing the subsequent causal PIT, each new DedupRun
created a new run-scoped algorithm decision and a new
`DedupReviewDecisionApplication`. Advancing the cutoff to include that derived application and
rebuilding Dedup therefore created another derived application after the new cutoff. Repeating the
same rule cannot converge.

The affected provisional DedupRuns, Premium runs, and applications are immutable operational
evidence. They are not deleted, retimestamped, retargeted, or promoted into a completed cycle.

## 2. Input evidence and derived output are distinct

The PIT `as_of` timestamp governs scientific **input evidence** selected by a DedupRun. A human
DedupDecision may influence the run only when the decision and all material source evidence are
causally available at or before `as_of` and the frozen material reconstruction matches exactly.

A `DedupReviewDecisionApplication` created for a new target algorithm decision is a run-scoped
**derived output/provenance artifact**. Its target algorithm decision and the application itself are
materialized while computing the run and may therefore have `created_at > DedupRun.as_of`. Their
creation timestamps remain truthful. They are not backdated.

The run's scientific consequence derives from the already-causal source human decision plus the
exact target material, not from pretending that the newly materialized application existed before
the run.

## 3. Corrected cutoff rule

The cycle retains one exact final cutoff shared by Dedup, Premium, Dashboard, and readiness.
Geospatial evidence created after a provisional cutoff remains a new scientific input for
Dashboard and therefore advances the cutoff once as already governed by GATE-013.

After that advance, rebuilding Dedup may create target-specific continuity applications as derived
outputs. Those output creation timestamps do not require another cutoff advance when:

- the source human decision was available by the final cutoff;
- the complete target pair evidence selected by the run was available by the final cutoff;
- the frozen material fingerprint reconstructs identically;
- the application is attached to the exact target algorithm decision;
- no human decision, observation, lifecycle event, or other scientific input was created after the
  final cutoff and consumed by the run.

A newly created or changed scientific input still fails closed or requires a separately governed
cutoff advance. This correction does not permit future evidence to leak backward.

## 4. Identity and history

New cycles bind:

- `cycle_version = daily-observatory-cycle-v0.4`;
- a new bounded cutoff-policy identifier encoding the input/output distinction;
- the existing geospatial-v0.2, privacy, provider, RAW-lineage, Source cohort, Dedup, Premium,
  Dashboard, freshness, and Day-0 authorities.

Completed v0.1, v0.2, and v0.3 cycles replay under their stored configuration only. Incomplete or
failed older cycles cannot resume as v0.4. Exact v0.4 retry remains mutation-free and performs no
Source or provider HTTP.

## 5. Integrity boundaries

This correction introduces:

- no Source collection method or Source request;
- no geocoder/provider request during implementation acceptance;
- no new human decision;
- no retargeting or mutation of continuity applications;
- no change to dedup material, thresholds, or outcomes;
- no change to Premium, Dashboard, geospatial, privacy, freshness, or Day-0 semantics;
- no authorization-policy change and no Day-0 unlock;
- no schema migration unless independently proven necessary;
- no scheduler activation before merge and production acceptance.

## 6. Acceptance

Tests must prove:

1. v0.4 configuration and cutoff-policy identity are explicit and deterministic;
2. a causal source human decision plus identical target material can produce a run-scoped
   application after `as_of` without triggering an unbounded second advance;
3. the application preserves its real `created_at`, exact target decision, source decision, and
   material fingerprint;
4. a future source human decision, changed material, conflicting authority, or future scientific
   input remains unavailable/fail-closed;
5. the geospatial one-advance path completes with aligned Dedup, Premium, Dashboard, and readiness
   at one exact final cutoff;
6. no Dashboard or readiness is created after a genuine second geospatial input advance;
7. historical cycles and the provisional production artifacts remain unchanged;
8. exact successful retry reuses the completed cycle with zero HTTP and zero new scientific
   artifacts;
9. focused and full regression suites, Ruff, mypy, Django checks, and migration-drift checks pass.

Passing mechanical checks means ready for independent semantic audit. It does not itself authorize
merge or production scheduling.

## 7. Post-merge production order

After independent audit and merge:

1. synchronize clean production `main`;
2. verify database and RAW backups and the operational RAW sentinel;
3. build one new manual v0.4 cycle or corrected no-Source-HTTP PIT acceptance as governed;
4. verify the exact v0.2 geospatial set, aligned downstream artifacts, 13 public markers, blocked
   Day-0 state, and exact retry;
5. start the web application and perform browser smoke acceptance;
6. activate the external scheduler only after the manual cycle and retry pass.
