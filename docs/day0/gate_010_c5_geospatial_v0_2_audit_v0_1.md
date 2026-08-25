# GATE-010-C5 — geospatial-v0.2 acceptance audit v0.1

## Authority and scope

- authoritative merged baseline: `99e39312535f33554a973110cba196c253628945`;
- stacked geographic-input base: `2c92cf6dc03c0cb49914319b045b51856d0cd3e6`;
- frozen contract commit: `2c2040e523845d513c0387486acab4dc81f359fa`;
- resolver: `geospatial-v0.2`;
- acceptance database: isolated copy `swiss_garden_jobs_gate010c5_acceptance`;
- acceptance RAW root: isolated `G:\SGJO-C5-RAW-ACCEPTANCE`.

The real operational database and RAW lineage were not modified. Source collector HTTP was zero.
The frozen research corpus and the C5 contract were not changed.

## Governed implementation

V0.2 preserves every `geospatial-v0.1` row and introduces a separate append-only resolver
identity. Municipality identity is established only from an existing Municipality FK, exact
locality plus governed canton, or the bounded Zürich Solique structured-place rule. Country and
canton normalization use finite Swiss aliases; no fuzzy, title, description, employer, or LLM
inference is used.

Municipality-only SearchServer requests are an exact `municipality + canton` projection with
`origins=gg25`. The provider's actual label-only representation, such as
`<b>Weesen (SG)</b>`, is parsed only under a strict `Municipality (CC)` grammar. Explicit fields
that contradict that label are rejected. Address candidates and multiple coordinate pairs do not
win municipality-only resolution.

Protected contexts keep their C2 privacy boundary: no raw-field municipality derivation, no
private canary in requests/evidence, and no public coordinates.

## Isolated preflight

The exact target was PremiumRun `76ece3d2-46c6-41a2-ba9e-da0467c37de4` with 51
`GREEN_CONFIRMED` assessments. Before mutation:

```text
selected                          51
existing geospatial-v0.2          0
PUBLIC_OR_NON_RESIDENTIAL        51

OBSERVATION_FK                    9
EXACT_LOCALITY_CANTON             7
GOVERNED_STRUCTURED_RAW_LOCATION  9
NONE                             26

targets with a request           32
unique requests                  23
no-request targets               19
```

Dry-run created no database evidence, RAW object, or provider request.

## Acceptance execution history

The first mutable attempt failed closed with `FileNotFoundError` because the isolated RAW root did
not yet contain nine cache objects referenced by the cloned database. The outer transaction left
zero v0.2 rows. A first cache-copy attempt then exposed a Windows path-length limitation in the
overly long temporary root and published no final object there.

The acceptance moved to the shorter external isolated root. Nine exact cache objects (37,009
bytes) were copied from read-only C4/C2 historical snapshots. Each object was found exactly once
and independently verified by logical object key, SHA-256, and byte size. No source root was
modified.

The governed batch then completed atomically:

```text
selected                       51
created                        51
RESOLVED                       13
REVIEW                         18
UNRESOLVED                     20
mappable                       13
cache applications             18
unique request identities      23
new provider requests          14
```

The transition matrix from the exact historical v0.1 target is:

```text
RESOLVED   -> RESOLVED           1
REVIEW     -> RESOLVED           3
REVIEW     -> REVIEW            18
UNRESOLVED -> RESOLVED           9
UNRESOLVED -> UNRESOLVED        20
```

All 18 review rows retain `MULTIPLE_PLAUSIBLE_RESULTS`. No ambiguous result was promoted.

Exact second geospatial execution returned 51 existing identities, zero creations, zero cache
reads, and zero provider requests.

## Historical preservation

The 51-target v0.1 result remains exactly `1 RESOLVED / 21 REVIEW / 29 UNRESOLVED`; all 595 v0.1
rows remain present. The accepted C3 PIT artifacts remain unchanged:

```text
Dedup      f9c92adf-3547-48d8-8b95-b569f40b9d42
Premium    76ece3d2-46c6-41a2-ba9e-da0467c37de4
Dashboard  a33ce5aa-45bb-4c0e-8bf3-82bef07dd92d
Readiness  c75f0e1d-f9df-4b89-89f7-0eea7b7dc3c7
```

The real operational database still contained zero `geospatial-v0.2` rows after acceptance.

## New causal PIT and replay

The new cutoff is one second after the latest v0.2 resolution:
`2026-08-25T03:03:43.806661Z`.

```text
Dedup
  ID           876b7ea7-5bbc-46e9-b8e7-ef97d1c78f9f
  fingerprint  ead076f070b8ce75e1a6b75f44d2b2d0ed26ab8574e5b680f833e3089cda9f6b

Premium
  ID           b9b525c3-ffd7-4824-94f9-3a60069ac34b
  fingerprint  54381a0b38e2297e05f72edb3cdbfc5aae436c887b72566c9d2ddf6ae7fe9c76

Dashboard
  ID           e55052f3-c567-4ed3-b0e3-93ac9bc7cdb7
  fingerprint  cdcd92b6d0b85eb466da557b761dcd37466cee4f2ee617532d1056ae5114d5df
  public GREEN 51
  mappable      13
  unmappable    38

Readiness
  ID           e86ede13-c186-4ff0-953a-aac03d64bbf7
  fingerprint  dd2763bb18e09debffd5c9d604af052ce0ed963d45e118abef2dde4471521c27
  status       DAY_0_NOT_READY
```

Day-0 has zero fresh eligible sources at this later cutoff because the acceptance copy contains
August 14 collection evidence. This is a causal freshness consequence, not a regression in the
geospatial result. Exact replay reused all four artifacts with identical IDs and fingerprints.

## Validation

```text
Focused C5/C2/C3/geographic    73 passed
Full pytest                   561 passed
Playwright                      4 passed
Ruff                            PASS
mypy                            PASS — 170 source files
Django check                    PASS
makemigrations drift            NONE
PostgreSQL clean migration      PASS
PostgreSQL existing copy        PASS — no migrations to apply
reference import x2             PASS — stable counts
exact geospatial replay         PASS
exact PIT replay                PASS
Source HTTP                        0
provider HTTP                     14 — isolated first execution only
real operational DB writes         0
migrations introduced              0
```

Exact-head CI, GitGuardian, H1, and review-thread results are recorded after the implementation
head is frozen and pushed for independent audit.
