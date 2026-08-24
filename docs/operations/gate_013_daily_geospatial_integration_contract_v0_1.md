# GATE-013 — Daily geospatial integration contract v0.1

Status: `FROZEN_FOR_IMPLEMENTATION`

- Baseline: merged GATE-010-C4 `99e39312535f33554a973110cba196c253628945`
- Prior cycle: `daily-observatory-cycle-v0.1`
- New cycle: `daily-observatory-cycle-v0.2`
- Resolver: `geospatial-v0.1`
- Privacy policy: `location-privacy-v0.1`
- Provider contract: `geo-admin-searchserver-api-2026-08`

## 1. Purpose and scope

GATE-013 integrates the already-governed geospatial resolution stage into routine daily
orchestration. It changes operational ordering and cycle identity only. It does not change Source,
Posting, Vacancy, lifecycle, review authority, Dedup, Premium, geography, privacy, Dashboard,
Day-0, RAW identity, provider, or authorization semantics.

The governed order becomes:

```text
collection
-> green continuity
-> Dedup
-> dedup continuity and aligned Dedup replay when required
-> Premium
-> geospatial resolution
-> Dashboard
-> Day-0 readiness
-> immutable completed cycle
```

`daily-observatory-cycle-v0.1` evidence remains historical and is never reinterpreted.

## 2. Cycle identity and configuration

The v0.2 configuration fingerprint binds the complete v0.1 material plus:

- cycle version `daily-observatory-cycle-v0.2`;
- the geospatial stage in its exact position after Premium and before Dashboard;
- resolver, privacy, provider, and RAW-lineage versions;
- the configured operational RAW manifest identity.

An exact retry requires the same configuration fingerprint. A v0.1 cycle ID cannot be retried as
v0.2 and a v0.2 cycle ID cannot be interpreted under v0.1.

## 3. Target universe and causality

The stage derives its complete target universe from the exact PremiumSegmentRun pinned by the
cycle. It uses the same final causal cutoff selected by the orchestrator for Dedup, Premium,
Dashboard, and readiness.

Only geospatial evidence with all required dependencies causally available at that cutoff may
influence the Dashboard. If the stage creates new resolution, cache, RAW metadata, or review
evidence after the provisional cutoff, the orchestrator advances the final cutoff beyond that
evidence, rebuilds/reuses the aligned Dedup and Premium artifacts, reruns geospatial resolution for
the newly aligned Premium run, and then builds Dashboard and readiness at the exact final cutoff.

The advance is bounded and deterministic. If a second advance would be required without an
explained new causal input, the cycle fails closed rather than looping indefinitely.

## 4. Geospatial execution

The stage uses only the governed Premium-target entrypoint and preserves the C2/C3/C4 contracts:

- exact Premium assessment and PostingObservation identity;
- exact privacy context;
- batch-wide resolution-identity preflight before provider or mutation;
- one outer database transaction for all new geospatial database evidence;
- immutable RAW publication and canonical operational RAW lineage;
- protected-location municipality/canton routing;
- no Source collector HTTP;
- no forced coordinate, marker, or human adjudication.

Outcomes remain `RESOLVED`, `REVIEW`, and `UNRESOLVED`. Only already-governed public display
coordinates may become map markers.

## 5. Idempotence, retry, and provider activity

An exact successful retry returns the stored completed-cycle result and performs no Source or
provider HTTP. A resumed cycle with an already-completed identical geospatial stage reuses its
pinned result. Re-executing an incomplete stage reuses exact resolution/cache/RAW evidence and
requests only evidence not already governed and cached.

The cycle records selected, existing, created, resolved, review, unresolved, cache-hit, and
provider-request counts. A zero provider-request claim is emitted only from actual instrumentation.

## 6. Failure taxonomy and status

The cycle adds persisted stage `geospatial`. Its statuses remain `PENDING`, `RUNNING`, `SUCCEEDED`,
`SKIPPED`, and `FAILED`.

Add terminal status `FAILED_GEOSPATIAL` and command exit code `10` for geospatial resolution,
privacy, RAW-lineage, provider-evidence, or geospatial causality failure. Existing exit codes 0 and
2–9 retain their v0.1 meanings.

A provider outage or ambiguity never invents coordinates. Governed `REVIEW`/`UNRESOLVED` outcomes
may still allow a technically successful cycle and usable table when the batch itself completes
validly. A contract, identity, privacy, storage, or batch failure is technical and fails closed.

Failures preserve completed Source attempts and all pre-existing immutable evidence. No downstream
Dashboard or readiness artifact is built from a failed geospatial stage.

## 7. Quality, status, and alerts

`observatory_status --json` adds a deterministic geospatial dimension containing bounded counts
for resolved, review, unresolved, mappable, public-but-unmapped, provider requests, and cache reuse.
Missing evidence is reported as missing, never as zero.

Append-only alert codes add `GEOSPATIAL_STAGE_FAILED` and `GEOSPATIAL_PROVIDER_DEGRADED`. Repeated
unchanged `REVIEW`/`UNRESOLVED` structural evidence does not create daily alert spam. The Dashboard
table remains available when no basemap or marker is available.

## 8. Concurrency and timeout

The existing PostgreSQL cycle advisory lock covers the geospatial stage. A losing invocation
performs zero Source and provider requests. Whole-cycle timeout checks apply before and after the
stage and seal a governed technical failure without discarding prior attempts. A real crash may
leave `RUNNING` evidence for existing stale-cycle recovery.

## 9. Integrity boundaries

GATE-013 introduces:

- no new Source collection method;
- no blocked-Source request;
- no change to the 29-Source denominator or 24/29 minimum;
- no change to green, dedup, Premium, Dashboard, freshness, or Day-0 policy;
- no human green, dedup, or geospatial decision;
- no mutation of historical cycles or PIT artifacts;
- no destructive RAW cleanup;
- no production scheduler activation.

Real production execution remains outside this implementation gate until independently audited.

## 10. Acceptance requirements

Tests must prove:

- exact stage ordering and v0.2 configuration fingerprinting;
- v0.1/v0.2 cycle-ID mismatch fails closed;
- exact Premium target and privacy-context routing;
- no Source HTTP in the geospatial stage;
- exact cache reuse and zero unnecessary provider calls;
- protected privacy and unresolved/review preservation;
- new geospatial evidence advances the cutoff and produces an aligned final PIT;
- no new evidence reuses the original cutoff and artifacts;
- geospatial batch failure yields `FAILED_GEOSPATIAL` / exit 10 and no Dashboard/readiness;
- provider ambiguity may complete with honest unmapped evidence;
- exact successful retry returns identical IDs/fingerprints with zero HTTP;
- real PostgreSQL concurrency loser performs zero provider activity;
- timeout, stale recovery, deterministic status, immutable prior cycle, and alert deduplication;
- historical v0.1 cycle and Dashboard snapshots remain unchanged.

Acceptance uses isolated databases and distinct RAW roots. It performs no real Source collection,
no real operational DB mutation, and no publication to the canonical operational RAW root.
