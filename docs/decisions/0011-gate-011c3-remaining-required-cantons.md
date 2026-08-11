# ADR 0011: GATE-011C-3 remaining required cantons

- Status: Accepted for implementation
- Date: 2026-08-11
- Baseline: `19b7baeaf8847e8e453b98388a598a0fc19394a0`

## Decision

GATE-011C-3 evaluates exactly AI, FR, GL, GR, JU, NW, OW, SH, SO, SZ, TG, UR and VS under their frozen `SRC-OFF-CANTON-*` identities. Reconnaissance precedes implementation and live technical evidence, rather than frozen platform labels, determines clustering.

`FULL_SOURCE` means all observable vacancy surfaces belonging to the canonical canton-employer identity. Apprenticeships, practica, teaching and temporary categories cannot be omitted merely because they use another presentation or are unlikely to be green. A careers-portal publication is not automatically a vacancy: the frozen observation contract requires an underlying employment opportunity.

The verified implementation clusters are:

- Refline: GR, with ordinary-employment and actual-apprenticeship vacancy surfaces.
- Configured Prospective: SO and SZ, each exact-source authorized and using its own frozen platform family.
- Blocked: AI, FR, GL, JU, NW, OW, SH, TG, UR and VS.

Every source therefore has one terminal result: GR/SO/SZ are `ACCEPTED_IMPLEMENTED`; the other ten are `ACCEPTED_BLOCKED`. Blocked sources receive no production adapter, endpoint or collection run and remain required in the Day-0 denominator.

For GR, Refline `stage.html` is an observed `NON_VACANCY_SOURCE_SURFACE`. Its
`Schnupperlehre` publications describe short trial/orientation experiences, not
underlying employment opportunities. They are excluded before Posting promotion;
this is an entity-boundary decision, not a green-classification rule. Genuine
`Lehrstelle` publications on `apprentice.html` remain in scope.

## Architecture and invariants

Adapters translate listing/detail evidence only. `SharedCollectionPipeline` remains the sole owner of governed HTTP, immutable RAW/SHA evidence, posting identity, append-only observations, green assessment, lifecycle, health and FULL_SOURCE promotion.

Adapter authorization remains exact-source. A matching vendor or frozen family does not activate another source. For multi-surface sources, every surface must complete; duplicate native IDs with one canonical detail collapse, while conflicting details fail closed. An incomplete surface or detail failure creates no negative lifecycle evidence.

Publication, update and first-seen timestamps remain distinct. Date-only evidence remains `EXACT_DATE`; missing evidence remains unknown. Workplace municipality is derived only from explicit source location evidence.

## Access decision

Only verified official acquisition origins for GR, SO and SZ are promoted. Reconnaissance-discovered redirects do not authorize origins at run time. Production acquisition remains governed GET/POST; no browser automation is introduced.

## Consequences

This gate completes the first-pass assessment of the 13 remaining canton sources without attempting to resolve the existing AG, BE, LU, SG canton or Stadt St. Gallen blockers. Job-Room remains outside scope.

GATE-008, GATE-009, GATE-010, GATE-011A, GATE-011B, GATE-011C-1 and GATE-011C-2 semantics are unchanged. Frozen research is unchanged.

Day-0 remains unauthorized. Coverage is diagnostic only; threshold and freshness policies remain `PENDING`.
