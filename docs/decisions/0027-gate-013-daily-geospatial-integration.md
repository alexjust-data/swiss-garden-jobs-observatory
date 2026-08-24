# ADR 0027 — GATE-013 daily geospatial integration

- Status: Accepted for implementation
- Baseline: `99e39312535f33554a973110cba196c253628945`
- Contract-only commit: `5e6e7d6acf186f0ad60ea764dc74660ad15b4875`
- Contract: `docs/operations/gate_013_daily_geospatial_integration_contract_v0_1.md`

## Context

GATE-012 established `daily-observatory-cycle-v0.1` without a geospatial stage. GATE-010-C2
explicitly prohibited adding that stage inside C2 and required a later versioned operations gate.
C2/C3/C4 subsequently established governed resolution, batch atomicity, immutable RAW identity and
one designated operational RAW lineage.

Without routine integration, a daily cycle can build a valid Dashboard before newly created
geospatial evidence is causally available. Manual geospatial recovery also does not provide an
autonomous daily operating path.

## Decision

Introduce `daily-observatory-cycle-v0.2`. The only scientific-pipeline ordering change is:

```text
Premium -> governed geospatial resolution -> Dashboard -> readiness
```

The v0.2 configuration fingerprint binds the exact stage order, cutoff policy, resolver, batch,
privacy, provider, RAW-lineage version and configured RAW manifest identity. The PostgreSQL lock
namespace remains shared with v0.1 so two deployed cycle versions cannot run concurrently.
Persisted running-cycle detection is also cross-version for the same governed cohort.

The geospatial stage uses the exact Premium run. When it creates evidence after the provisional
cutoff, the orchestrator advances the cutoff once, rebuilds/reuses aligned Dedup and Premium, and
reruns the geospatial batch. A second unexplained causal advance fails closed. Dashboard and
readiness are built only after a successful aligned stage.

The cycle persists bounded geospatial counts, exact resolution IDs, provider/cache activity and
whether the cutoff advanced. It adds terminal `FAILED_GEOSPATIAL`, stage-specific alerting and CLI
exit code 10. Transport/SearchServer failures additionally emit `GEOSPATIAL_PROVIDER_DEGRADED`;
identity, privacy and RAW failures are not mislabeled as provider outages.

## Compatibility and immutability

Historical v0.1 cycles and PIT artifacts remain unchanged. A v0.1 cycle configuration cannot be
resumed as v0.2. A completed v0.2 exact retry returns its stored result before collection or
geospatial activity.

Migration `operations/0002_add_failed_geospatial_status.py` changes only the Django status choices;
it does not rewrite cycle rows.

## Consequences

- Daily operation can materialize current governed map evidence before Dashboard construction.
- Provider ambiguity remains honest `REVIEW`/`UNRESOLVED`; marker count is never a success target.
- An operational RAW designation is a deployment prerequisite for real v0.2 execution.
- GATE-013 does not activate a scheduler and does not authorize the first real production run.
- Existing Source, review, Dedup, Premium, Dashboard and Day-0 semantics remain frozen.

