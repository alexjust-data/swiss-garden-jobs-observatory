# ADR 0031 — GATE-013-C2 derived-output causality

## Status

Proposed for independent audit.

## Context

GATE-012 and GATE-013 required aligned PIT artifacts and bounded cutoff advancement. The first real
geospatial-v0.2 acceptance proved that geospatial evidence could be created and exactly replayed,
but the following PIT build revealed that Dedup continuity applications are target-run outputs.
Each aligned Dedup rebuild creates a new target algorithm decision and therefore a new append-only
application. Advancing the cutoff to include each new application cannot terminate.

The frozen GATE-011G material contract remains correct: a future application cannot be used as
historical inherited authority. In this path, however, the already-causal human decision is the
authority consumed by the run. The newly created application records the exact target-specific
reuse as output provenance.

## Decision

Adopt `daily-observatory-cycle-v0.4` and cutoff policy
`causal-inputs-and-derived-outputs-aligned-pit-v0.3`.

The PIT cutoff governs selected scientific inputs. Run-scoped algorithm decisions and their exact
continuity applications may be materialized after `DedupRun.as_of` because they are outputs of that
computation. They retain truthful creation timestamps and remain unavailable as prior application
evidence at an earlier cutoff.

The orchestrator validates every application attached to its DedupRun against the frozen material
configuration and requires the source human decision to predate or equal the cutoff. It does not
advance the cutoff merely because those derived outputs were materialized.

New geospatial resolution evidence remains an input for Dashboard construction and still advances
the cutoff once. A second unexplained geospatial input advance remains a technical failure.

## Consequences

- the cycle reaches a finite, causally aligned Dedup/Premium/Dashboard/readiness chain;
- no human knowledge or derived application is backdated;
- no historical cycle or provisional artifact is rewritten;
- completed v0.1, v0.2, and v0.3 cycles retain exact replay;
- incomplete older cycles cannot resume under v0.4;
- Day-0 policies and the blocked authorization result do not change;
- no migration is required.

## Operational boundary

Production scheduling remains disabled until C2 is independently audited and merged, one manual
v0.4 cycle and exact retry succeed, the 13 v0.2 public markers are verified, and the status/backup
surfaces pass their production smoke checks.
