# GATE-013 — Daily geospatial integration acceptance v0.1

## Authority and scope

- Baseline: `99e39312535f33554a973110cba196c253628945`
- Branch: `codex/gate-013-daily-geospatial-integration`
- Contract-only commit: `5e6e7d6acf186f0ad60ea764dc74660ad15b4875`
- Contract file SHA-256: `7fd380630cef6132183d01d4a57c34931e1a0f243383f21533c33edac2931784`
- Final implementation head: pinned in the PR and final handoff after commit
- State: isolated acceptance; production execution not authorized

The frozen contract was committed alone before implementation. GATE-013 changes operational cycle
ordering and identity only. It changes no frozen research or scientific policy.

## Implemented behavior

`daily-observatory-cycle-v0.2` runs:

```text
cohort -> collection -> green continuity -> Dedup -> dedup continuity
-> Premium -> geospatial -> Dashboard -> readiness
```

The configuration binds the geospatial batch, resolver, privacy, provider, RAW lineage and
operational manifest identity. Completed v0.1 identities cannot be reinterpreted as v0.2.

The stage records selected/existing/created and `RESOLVED`/`REVIEW`/`UNRESOLVED`, mappable,
public-but-unmapped, hidden, cache, provider and resolution-ID evidence. Exact full reuse is exposed
separately from a run that created new evidence.

New geospatial evidence causes one bounded causal realignment. The final Dedup, Premium, Dashboard
and readiness artifacts share the advanced cutoff. A second required advance fails closed with
`GEOSPATIAL_REALIGNMENT_REQUIRES_SECOND_CUTOFF` before Dashboard construction.

## Failure and retry evidence

- geospatial contract/batch failure -> `FAILED_GEOSPATIAL`;
- CLI exit -> 10;
- timeout at the stage -> terminal `FAILED_GEOSPATIAL` / `CYCLE_TIMEOUT`;
- Dashboard/readiness remain absent after stage failure;
- provider transport/SearchServer failure emits `GEOSPATIAL_PROVIDER_DEGRADED`;
- non-provider privacy/identity/RAW failure does not emit that provider alert;
- PostgreSQL concurrency refusal records Source HTTP 0 and provider requests 0;
- exact completed-cycle retry invokes neither collector nor geospatial runner.

## PostgreSQL migration acceptance

Migration: `operations/0002_add_failed_geospatial_status.py`.

Clean database `swiss_garden_jobs_gate013_clean_20260825` migrated from zero successfully.

Existing restored copy `swiss_garden_jobs_post_c4_verify_20260824` migrated successfully and
retained exact bounded counts:

```text
RawArtifact                     10917
PostingLocationResolution        556
GeocoderCacheEntry                  3
GeocodingReviewItem                80
PremiumSegmentRun                  19
DashboardSnapshot                  19
Day0ReadinessAssessment            18
```

The real `swiss_garden_jobs` database retained the same counts and did not receive
`operations.0002` during acceptance.

## Validation

```text
operations suite                         65 passed
operations/C2/C3/C4/Dashboard matrix    204 passed
full pytest                             540 passed
Playwright browser                        4 passed
Ruff lint                              PASS
Ruff format — seven changed code files PASS
mypy                                   PASS — 167 source files
Django check                           PASS
makemigrations --check --dry-run       PASS — no drift
PostgreSQL clean migration             PASS
PostgreSQL existing-copy migration     PASS
```

The repository-wide Ruff formatter reports pre-existing format drift in 36 unrelated mainline
files. They were not rewritten in this scoped PR. Repository-wide Ruff lint passes and every
changed GATE-013 code file passes the formatter.

## Stacked integration reconciliation

A clean rehearsal stacked GATE-013 with the later governed `geospatial-v0.2` implementation and
proved that importing the module-level current resolver/batch constants would silently change this
cycle's frozen configuration from v0.1 to v0.2. The combined suite failed exactly at that identity
boundary.

The correction does not change the frozen GATE-013 contract. Daily orchestration now pins
`geospatial-resolution-batch-v0.1` and `geospatial-v0.1` explicitly and constructs its default
resolver with that version. The later C5 batch exposes v0.1 and v0.2 as distinct supported
identities while retaining v0.2 as its explicit current default. A regression test proves the daily
runner passes a v0.1 resolver instead of inheriting future module-level drift.

The corrected clean integration rehearsal passed 77 focused tests, 641 full tests, four browser
tests, Ruff, mypy over 177 source files, Django check, migration drift, clean PostgreSQL migration,
and reference import twice. The rehearsal used only an isolated PostgreSQL container; production
and the frozen contract remained unchanged.
## Integrity and remaining boundary

```text
real operational DB writes       0
canonical operational RAW writes 0
Source HTTP                       0
geocoder/provider HTTP            0
human adjudication                0
historical cycle mutation         0
historical PIT mutation           0
```

GATE-013 is ready for mechanical H1 verification and independent semantic audit after its exact
head is pushed. It must not be executed against production until C4 consolidation and real
geospatial recovery have crossed their separately audited production boundary.
