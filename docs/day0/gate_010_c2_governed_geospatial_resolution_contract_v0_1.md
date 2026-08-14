# GATE-010-C2 — Governed geospatial resolution contract v0.1

## Status and predeclaration

This contract is frozen before measuring current-corpus geospatial outcomes or making any
geo.admin.ch request for GATE-010-C2.

- Baseline: `6669bd8a852b53a722685cec24949cf5180c30a1`
- Merged gate: GATE-010-C1 / PR #27
- Resolver: `geospatial-v0.1`
- Privacy policy: `location-privacy-v0.1`
- Provider contract: `geo-admin-searchserver-api-2026-08`
- Provider: geo.admin.ch SearchServer
- Map: MapLibre with official swisstopo WMTS tiles

This gate does not redefine location precision, privacy, Premium, Dedup, Dashboard, Day-0 or
Source semantics.

## Scientific question

For an immutable PostingObservation already selected by governed PIT evidence, can the existing
resolver derive an auditable location and a privacy-safe public display coordinate from exactly
the evidence available at a new causal cutoff?

The direction is:

```text
existing immutable observation
+ causal Premium privacy context
+ frozen resolver/provider/privacy versions
-> immutable resolution evidence
-> resolved / review / unresolved
-> privacy-safe public coordinates or no coordinates
-> new PIT snapshot
```

Desired marker counts must never choose resolution rules.

## Scope

GATE-010-C2 will:

1. select a deterministic target observation universe from one exact accepted Premium run;
2. carry the exact Premium assessment identity and privacy context for every target;
3. resolve only targets capable of becoming public green dashboard records;
4. use existing immutable cache, RAW, resolution and review evidence models;
5. build a new causally aligned downstream PIT after resolution evidence is available;
6. prove exact replay and historical snapshot immutability;
7. report actual resolved, review, unresolved, hidden and publicly mappable counts;
8. harden the default swisstopo basemap failure message without changing map evidence.

GATE-010-C2 will not:

- recollect a Source or request a job-advertisement URL;
- recover blocked Sources;
- mutate an old PostingObservation, location resolution, DashboardSnapshot or readiness artifact;
- retarget a resolution to another observation;
- create human review decisions;
- resolve ambiguity merely to produce more markers;
- use fuzzy matching, embeddings, LLM geocoding or Google geocoding;
- introduce Google Maps billing as a production dependency;
- integrate a new geospatial stage into the frozen `daily-observatory-cycle-v0.1` contract.

Routine-cycle integration requires a later versioned operations gate after C2 acceptance.

## Target universe

The acceptance target is derived from one exact, immutable PremiumSegmentRun and its assessments,
not from the mutable current dashboard page and not from a hard-coded count.

A target must:

- belong to the selected Premium run;
- reference the exact PostingObservation selected by that run;
- be causally available at the declared input cutoff;
- have an effective green result capable of public dashboard visibility under frozen policy;
- carry a supported `privacy_context`.

The command must pin and report the Premium run ID, its input fingerprint, input cutoff, selected
assessment IDs and selected observation IDs. Duplicate observations with conflicting privacy
contexts fail closed.

## Privacy-context routing

The existing generic `resolve_locations --source-id` command is not the governed C2 batch entrypoint
because it defaults every observation to `PUBLIC_OR_NON_RESIDENTIAL`.

C2 must introduce a deterministic entrypoint that calls `GeospatialResolver.resolve()` with the
exact causal Premium assessment context:

- `PUBLIC_OR_NON_RESIDENTIAL`: source structured coordinates or bounded location evidence may be
  resolved according to `geospatial-v0.1`;
- `PRIVATE_RESIDENCE`: the outbound request must omit street and postcode-level private evidence
  and use the frozen generalized municipality/canton representation;
- `CONFIDENTIAL_PRIVATE_RESIDENCE`: the same protected request boundary applies and public display
  remains governed by `location-privacy-v0.1`.

No raw/private street, house number, description text, contact data or confidential employer data
may enter a protected geocoder request, log, report, frontend payload or Google Maps URL.

## Provider and request contract

Allowed network activity is limited to governed HTTPS GET requests to:

`https://api3.geo.admin.ch/rest/services/api/SearchServer`

Requests must preserve the existing same-origin redirect rule, bounded parameter allowlist,
WGS84 output (`sr=4326`), response size limit, content-type validation, User-Agent and timeout.

Every accepted response must retain immutable RAW bytes, SHA-256, requested/final URL, provider
version, request fingerprint and cache identity. Exact cached requests are reused. A provider
failure creates no coordinate and no negative Source/lifecycle evidence.

No Source collector HTTP is authorized by this gate.

## Outcomes

The resolver's frozen outcomes remain:

- `RESOLVED`: deterministic evidence supports one location;
- `REVIEW`: contradiction, ambiguity or unsupported evidence requires review;
- `UNRESOLVED`: no governed resolution is available.

Only `RESOLVED` evidence with a non-hidden privacy display level and a complete finite public
coordinate pair is `MAPPABLE`.

`REVIEW`, `UNRESOLVED`, `HIDDEN`, missing coordinate pairs and invalid coordinates never become a
marker. They remain visible in the public vacancies table only when other dashboard visibility
rules allow it, with the explicit not-shown-on-map presentation from GATE-010-C1.

## Identity, append-only evidence and idempotence

Resolution identity includes:

- PostingObservation UUID;
- resolver version;
- privacy context;
- deterministic input fingerprint.

An existing identical resolution is reused. A row may never be moved to a newer observation or a
different privacy context. Conflicting evidence under the same governed identity fails closed.

Exact replay of the same target universe must:

- create no duplicate PostingLocationResolution;
- create no duplicate GeocoderCacheEntry or RAW artifact for an identical cached request;
- create no duplicate GeocodingReviewItem;
- return the same resolution/review IDs and classifications;
- perform zero provider requests when all required responses/evidence are already cached.

Concurrent identical resolution attempts must converge to one authoritative evidence row or fail
closed without partial contradictory authority.

## Causality and PIT reconstruction

Resolution evidence may influence cutoff `T` only when its `created_at <= T`. Geocoder RAW/cache
evidence and any review item on which the resolution depends must also be available by `T`.

The old dashboard snapshots remain unchanged. After resolution:

1. choose a new cutoff after all accepted C2 evidence is available;
2. build/reuse an aligned Dedup run at that cutoff;
3. build/reuse the aligned Premium run;
4. build a new DashboardSnapshot at the same cutoff;
5. build the aligned Day0ReadinessAssessment;
6. replay the exact inputs.

Dedup, Premium and Day-0 semantics do not change. Geospatial evidence may change map/materialization
counts but must not manufacture Day-0 authorization or headline values.

## Public map and Google Maps URLs

The GeoJSON endpoint remains the sole browser marker source. It must continue independently to
require public green visibility, `MAPPABLE`, `RESOLVED`, non-hidden privacy and finite public
coordinates.

The embedded map remains the free official swisstopo basemap. An outbound Google Maps URL may be
constructed only from the already-filtered public GeoJSON coordinate pair. Raw location text is
never used in that URL.

The default swisstopo error path must show a bounded basemap-unavailable message while preserving
the complete table and any safely mappable overlay evidence.

## Acceptance measurement

After this contract-only commit, C2 will report without count targets:

- selected Premium assessments and unique observations;
- existing identical resolutions;
- new resolutions;
- provider requests and cache hits;
- `RESOLVED`, `REVIEW`, `UNRESOLVED`;
- public exact, postcode, municipality and region display precision;
- hidden/private generalizations;
- mappable and public-but-unmapped records;
- review reasons and bounded item-level lineage;
- new PIT artifact IDs/fingerprints and Day-0 consequence.

No private or unnecessary contact/location payload may enter committed audit documents.

## Failure and stop conditions

C2 stops before target mutation when:

- the selected Premium run or target universe is not deterministic;
- one observation has conflicting causal privacy contexts;
- protected request construction includes private street-level evidence;
- an existing resolution conflicts under the same identity;
- the provider response cannot be preserved and verified;
- historical artifacts would need mutation;
- any frozen scientific contract would need a semantic change.

Provider ambiguity is not a gate failure: it becomes governed `REVIEW` or `UNRESOLVED` evidence.

## Validation obligations

Focused tests must cover public, private and confidential request boundaries; structured source
coordinates; municipality/postcode resolution; ambiguity/review; no-result unresolved; invalid
coordinates; cache reuse; concurrency; historical cutoff exclusion; GeoJSON filtering; Google URL
privacy; swisstopo failure fallback; new PIT creation; historical snapshot immutability; and exact
replay.

The final gate also requires the complete regression, browser, Ruff, mypy, Django, migration,
PostgreSQL clean/existing and reference-import checks. Long-running validation is launched by the
operator using the command supplied by Codex.
