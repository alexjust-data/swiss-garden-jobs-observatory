# ADR 0024: GATE-010-C2 governed geospatial resolution

## Status

Accepted for implementation and isolated operational acceptance; pending independent audit.

## Context

GATE-010-C1 delivered the privacy-filtered GeoJSON endpoint and a free MapLibre/swisstopo map, but
the accepted production snapshot had no compatible location resolutions for its 51 public-green
observations. The generic source-based command could not be used safely because it defaults every
observation to a public privacy context.

Baseline: `6669bd8a852b53a722685cec24949cf5180c30a1`.

Frozen operating contract:
`docs/day0/gate_010_c2_governed_geospatial_resolution_contract_v0_1.md`, committed alone as
`25019f246eb1692e46e611396755b1112ed400c7`.

## Decision

Introduce `geospatial-resolution-batch-v0.1` and the command:

```text
python manage.py resolve_premium_locations --premium-run <UUID>
```

The batch accepts one exact successful PremiumSegmentRun, selects only assessments whose effective
green result is `GREEN_CONFIRMED`, pins all assessment/observation IDs and passes each assessment's
exact causal privacy context to `GeospatialResolver`.

`--dry-run` selects and reports the complete universe without resolver construction, provider
activity or evidence writes. Unsupported or conflicting privacy context fails closed. Existing
resolution identity is reused only if its input fingerprint still equals the independently
recomputed current governed input.

PostgreSQL transaction advisory locks serialize exact resolution identity and provider-request
cache identity. This makes concurrent identical attempts converge on one immutable resolution,
cache entry, RAW artifact and optional review item. Non-PostgreSQL test environments do not claim
this operational guarantee; the focused PostgreSQL contention test exercises it directly.

The default swisstopo error path now displays a bounded unavailability message for both default and
custom styles while the complete table remains usable.

## Privacy and provider boundary

Public/non-residential evidence may use frozen structured/location surfaces. Private and
confidential contexts use the pre-existing generalized municipality/canton request and never send
street-level evidence. Only geo.admin.ch SearchServer is allowed. Google links continue to derive
only from already-filtered public GeoJSON coordinates.

No Source collection, fuzzy matching, description geocoding, manual decision or historical
artifact mutation is introduced.

## Isolated acceptance

The accepted Premium input selected 51 public/non-residential observations. The governed result was
one resolved/mappable, 21 review and 29 unresolved. Ten distinct SearchServer request identities
were required; nine new responses were persisted and one cache entry was already present. Exact
replay performed zero provider requests and reused all 51 resolution IDs.

The low marker count is not optimized away. Twenty-eight targets had no normalized location fields,
ten had an unexpected country representation, eleven had multiple plausible candidates, one had
other insufficient evidence and one had an unambiguous structured coordinate. These findings are
an upstream extraction/normalization backlog, not permission to change `geospatial-v0.1` after
seeing outcomes.

At cutoff `2026-08-14T14:24:00Z`, the aligned artifacts are:

- DedupRun `2dc3b341-0be5-47b5-b726-cfa50604f86b`;
- PremiumSegmentRun `d87ffba2-6a1b-4d66-803a-574d97a14580`;
- DashboardSnapshot `45343909-18be-4e8e-87e9-55079d136fc1`;
- Day0ReadinessAssessment `22503245-af1d-4e75-afc3-36d891683db8`.

The downstream exact replay returned the same IDs and fingerprints. The historical GATE-012
snapshot remained 0 mappable / 51 unmappable; the new snapshot is 1 / 50. Day-0 remains
`DAY_0_BLOCKED_BY_DATA_QUALITY`, with 19/29 eligible Sources, three critical green reviews, 21
critical geospatial reviews, zero critical dedup reviews and a null headline.

## Consequences

The map can now materialize only genuinely supported coordinates. Most current records remain
explicitly marked as not shown on the map. A separate gate should improve source-specific location
extraction and country normalization before reconsidering unresolved/review evidence.

C2 does not modify `daily-observatory-cycle-v0.1`. Routine execution requires a later operational
cycle version whose order is collection, continuity, Dedup, Premium/privacy, geospatial resolution,
Dashboard and Day-0.

## C1 asset packaging correction

A clean-worktree browser run found that C1 referenced a local MapLibre vendor directory excluded by
`.gitignore`; the audited working tree had the assets, but the merge did not. C2 makes that existing
presentation dependency reproducible by tracking MapLibre GL JS 6.2.0 with its license:

- `maplibre-gl.css`: `c66d9ffcc734854c5aecac71c96d89e981268b4147ff3e4b1aebe08c83465400`;
- `maplibre-gl.mjs`: `d7aeac0511a743c15ba231ace5a74dbc4f514dd2a395c6c1504fedc313ae81a9`;
- `maplibre-gl-shared.mjs`: `7306565d651d8fdcca8ca5492ce55c1c6753468d1599144a3a914ccb51abe82b`;
- `MAPLIBRE-LICENSE.txt`: `ee5fc05a0677eaf69601d2c7db0d9ecd6cc27c3abc1d0733bc9ed34707cf8ef2`.

This correction adds no external runtime script origin, Google dependency or scientific semantic.

## Validation

The clean pre-audit head passed the complete 482-test suite, all seven focused C2 tests, four browser
tests, Ruff, mypy across 161 source files, Django check and migration-drift validation. Django
staticfiles resolves all four tracked MapLibre distribution/license files. Reference data was
imported twice with identical counts into the isolated acceptance database. The real operational
database was not modified and no Source collector HTTP request was made.

## Independent-audit correction

Independent audit of head `7decee4155999cc2113f5eac5b4e9e61843a6dbe` found that protected
request construction could prefer raw locality/region over governed Municipality/canton, and that
existing-resolution conflicts were checked sequentially rather than across the complete batch
before mutation.

The authoritative protected projection is now Municipality name plus canton with `origins=gg25`;
without a governed Municipality it performs no provider request. Resolver execution and batch
preflight share one canonical resolution input-material/fingerprint function. The batch validates
all existing identities before any target execution, including in dry-run mode, and fails without
provider, cache, RAW, resolution or review writes on any conflict. This enforcement correction
does not alter the frozen contract, thresholds, public-context behavior or historical acceptance
artifacts.

After correction, the complete suite passed 485 tests. The 20 combined focused C2 and legacy
geospatial tests cover both protected contexts, raw-field canaries, the no-Municipality no-request
path, canonical fingerprint equality, order-independent batch preflight, zero partial writes and
real PostgreSQL concurrency. Exact isolated replay reused the same 51 resolutions and four PIT
artifacts with zero provider requests or new evidence.
