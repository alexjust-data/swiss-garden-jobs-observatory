# ADR 0030 — GATE-013-C1 daily geospatial v0.2 promotion

## Status

Proposed for independent audit.

## Context

GATE-013 introduced `daily-observatory-cycle-v0.2` and deliberately pinned its
geospatial stage and Dashboard to `geospatial-v0.1`. GATE-010-C5 later merged
the separately governed `geospatial-v0.2`, whose isolated acceptance produced
13 safely mappable records instead of one. The daily cycle remained explicitly
pinned to v0.1, so enabling the scheduler at that point could create a new
Dashboard with the old one-marker authority.

Changing the geospatial authority inside the existing daily v0.2 identity would
rewrite its semantic meaning and make historical retry depend on current code.

## Decision

New cycles use `daily-observatory-cycle-v0.3`. Its immutable configuration pins:

- `geospatial-resolution-batch-v0.2`;
- `geospatial-v0.2`;
- Dashboard construction under the same `geospatial-v0.2` authority.

The constants are imported from the merged C5 implementation and are still
written explicitly into the cycle configuration fingerprint. The stage order,
causal cutoff realignment, Source cohort, privacy, provider, RAW lineage,
Premium, Dashboard and Day-0 rules are unchanged.

Completed v0.1, v0.2 and v0.3 cycles may be returned by exact cycle-ID retry
only after validating their stored configuration hash, cycle identity, cohort,
trigger and version-specific geospatial semantics. This replay occurs before
consulting the current Source cohort and performs no operational activity.
Incomplete v0.1/v0.2 cycles still fail configuration comparison and cannot be
resumed as v0.3.

## Consequences

- `daily-observatory-cycle-v0.2` continues to mean geospatial v0.1 forever.
- New production cycles cannot silently fall back from the merged v0.2 map
  authority to v0.1.
- Historical completed evidence remains exactly replayable without HTTP.
- No migration is required.
- Day-0 remains governed by the existing 24/29 and data-quality requirements;
  this correction neither authorizes nor weakens it.
- Production, RAW, Source and provider state remain untouched until independent
  audit and merge.

## Validation

- focused GATE-012/GATE-013: 32 passed;
- expanded operations/C5/Dashboard regression: 122 passed;
- full pytest: 660 passed, 2 skipped;
- Dashboard browser acceptance: 4 passed;
- Ruff: passed;
- mypy: passed for 177 source files;
- Django check: no issues;
- migration drift: none.

