# ADR 0027 — GATE-010-C5 governed geospatial resolution v0.2

## Status

Proposed for independent audit.

## Context

`geospatial-v0.1` correctly failed closed but produced only one public marker for the accepted
51-vacancy corpus. Later geographic-input analysis proved that bounded structured evidence could
establish additional exact Swiss Municipality identities without fuzzy matching or rewriting
historical observations.

The historical v0.1 identity cannot change. A new causal resolver identity is required.

## Decision

Introduce append-only `geospatial-v0.2` while retaining exact v0.1 replay.

V0.2 derives municipality identity only from:

1. the observation's Municipality FK;
2. exact locality within an exact governed canton;
3. the explicitly bounded Zürich Solique structured-place field.

Municipality-only provider requests use canonical municipality plus canton and `origins=gg25`.
Candidate acceptance requires a strict Swiss `gg25` municipality identity and one coordinate pair.
The official label-only response form `Municipality (CC)` is parsed with a closed grammar and
contradictory fields fail closed.

V0.2 preserves C2 privacy and C3 atomic RAW/cache/batch guarantees. It introduces no migration and
does not modify Premium, Dashboard, Day-0, Source acquisition, or frozen research semantics.

## Acceptance evidence

Against an isolated copy of the exact C3 target, v0.2 produced 13 resolved, 18 review, and 20
unresolved rows. Thirteen records are safely mappable. Fourteen new provider requests were made;
the exact retry made zero. A new causal Dashboard contains 51 public GREEN records, 13 mappable
and 38 unmappable. Its exact PIT replay reused Dedup, Premium, Dashboard, and Readiness.

All 18 remaining review rows have multiple plausible coordinate pairs. They remain review rather
than being promoted for presentation purposes.

## Consequences

- Historical v0.1 rows, API interpretation, and C3 artifacts remain unchanged.
- New markers become visible only through a DashboardSnapshot after v0.2 evidence is causally
  available.
- Production remains unchanged until independent audit and merge.
- More markers require better governed structured inputs or human geospatial adjudication; they
  cannot be obtained by weakening candidate selection.
