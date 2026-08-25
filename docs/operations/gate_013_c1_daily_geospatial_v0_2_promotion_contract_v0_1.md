# GATE-013-C1 — Daily geospatial v0.2 promotion contract v0.1

## Purpose

Promote newly created daily observatory cycles to the already merged
`geospatial-v0.2` authority before production scheduling begins, without
changing Day-0 policy, historical cycle meaning, scientific thresholds, privacy
rules, provider rules, or immutable evidence.

## Baseline and authority

- merged baseline: `01a28328161fedc77d7c7f6bec4039d9a75925e0`;
- prior daily authority: `daily-observatory-cycle-v0.2` with
  `geospatial-resolution-batch-v0.1` and `geospatial-v0.1`;
- promoted daily authority: `daily-observatory-cycle-v0.3` with
  `geospatial-resolution-batch-v0.2` and `geospatial-v0.2`;
- the merged GATE-010-C5 implementation determines the exact v0.2 resolver
  semantics;
- this correction does not redefine `geospatial-v0.1` or `geospatial-v0.2`.

Changing geospatial authority changes the daily cycle configuration identity.
Therefore the existing `daily-observatory-cycle-v0.2` label will not be reused
for the promoted configuration.

## New-cycle contract

Every newly created daily cycle must bind, in its immutable configuration and
configuration fingerprint:

- `cycle_version = daily-observatory-cycle-v0.3`;
- `geospatial_batch = geospatial-resolution-batch-v0.2`;
- `geospatial_resolver = geospatial-v0.2`;
- Dashboard construction to the same exact `geospatial-v0.2` authority;
- the existing stage order, causal realignment rule, RAW-lineage authority,
  privacy policy, provider policy, Source cohort, and Day-0 policies.

The default daily geospatial runner must instantiate the v0.2 resolver
explicitly. It must not depend on an implicit library default.

## Historical replay and recovery

Completed immutable cycles under `daily-observatory-cycle-v0.1` or
`daily-observatory-cycle-v0.2` remain exact historical evidence. An exact retry
by cycle ID must:

- validate the stored configuration fingerprint and bounded cycle identity;
- return the persisted completed cycle unchanged;
- perform no Source collection, geocoder/provider request, geospatial batch,
  Dashboard construction, or other downstream mutation;
- not reinterpret historical artifacts using `geospatial-v0.2`.

A failed, running, stale, or otherwise incomplete v0.1/v0.2 cycle must not be
resumed as v0.3. Configuration mismatch remains fail-closed. Only a new v0.3
cycle may use the promoted authority.

Tampered or internally inconsistent stored historical configuration is never
eligible for replay.

## Day-0 boundary

This gate does not authorize Day-0 and does not change:

- the 29-Source required denominator;
- the 24/29 structural minimum;
- Federal, canton, or city minima;
- freshness thresholds;
- review requirements;
- blocked-source dispositions;
- the current `DAY_0_BLOCKED_BY_DATA_QUALITY` consequence.

Production may operate and publish non-headline scientific evidence while
Day-0 remains blocked. Headline market counters remain unavailable until the
existing authorization contract is genuinely satisfied.

## Data and network boundary

Implementation and acceptance before merge must not:

- write the real operational database;
- modify the operational RAW corpus;
- recollect a Source;
- call the geocoding provider;
- mutate historical cycles or PIT artifacts;
- activate the scheduler.

Tests use deterministic fixtures, mocks, or isolated databases. No migration is
expected because version identities are persisted data values, not schema.

## Acceptance

The correction is accepted mechanically only when tests prove:

1. new configuration binds cycle v0.3 and geospatial batch/resolver v0.2;
2. the default runner and Dashboard both receive resolver v0.2;
3. completed v0.1 and v0.2 cycles replay exactly with zero activity;
4. stored-configuration tampering fails closed;
5. incomplete v0.1/v0.2 cycles cannot resume as v0.3;
6. v0.3 exact retry remains idempotent;
7. scientific, privacy, RAW, Dashboard, Day-0, and operational regressions pass;
8. the repository has no migration drift;
9. this contract remains byte-identical after its isolated predeclaration
   commit.

Passing mechanical checks means ready for independent semantic audit. It does
not by itself approve merge or production execution.

## Post-merge production order

Only after independent audit and merge:

1. synchronize merged `main`;
2. create and verify fresh database and RAW backups;
3. complete the already governed C4 operational RAW consolidation and sentinel
   verification;
4. apply pending merged migrations;
5. run the governed real geospatial v0.2 recovery and exact no-provider retry;
6. run one new manual daily cycle under v0.3 and its exact no-HTTP retry;
7. verify the real Dashboard/map and the continued Day-0 blocked state;
8. activate the external scheduler only after those checks pass.

