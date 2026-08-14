# GATE-010-C2 geospatial resolution audit v0.1

## Scope and provenance

- Baseline: `6669bd8a852b53a722685cec24949cf5180c30a1`.
- Frozen contract commit: `25019f246eb1692e46e611396755b1112ed400c7`.
- Resolver: `geospatial-v0.1`.
- Privacy policy: `location-privacy-v0.1`.
- Provider contract: `geo-admin-searchserver-api-2026-08`.
- Acceptance database: isolated copy `swiss_garden_jobs_gate010c2_acceptance`.
- Real operational database modified: no.
- Source collector HTTP: zero.

The target was derived after contract predeclaration from Premium run
`641fbb6c-25f0-451e-91c2-e3197be4a9d7`, fingerprint
`0a49c84401bcc5804c34573bcaa352fb4f61323420731a0576a608ee3856c35d`, with input
cutoff `2026-08-14T00:07:17.897427Z`.

## Governed target and resolution result

| Measure | Result |
|---|---:|
| selected green Premium assessments | 51 |
| unique selected observations | 51 |
| public/non-residential contexts | 51 |
| protected contexts in this corpus | 0 |
| prior compatible target resolutions | 0 |
| new immutable target resolutions | 51 |
| RESOLVED | 1 |
| REVIEW | 21 |
| UNRESOLVED | 29 |
| publicly mappable | 1 |
| public but unmapped | 50 |
| review items | 21 |

The first provider execution used ten distinct governed request identities. Nine required new
geo.admin.ch responses and one reused pre-existing immutable cache evidence. Repeated target
requests produced twelve cache reuses in the batch. The exact second execution returned all 51
resolution IDs, created zero rows, and performed zero provider requests.

No marker-count target influenced these outcomes.

## Bounded failure lineage

The unresolved/review distribution is explained without copying raw locations:

| Evidence class | Count | Governed consequence |
|---|---:|---|
| no normalized street/locality/postcode/region/municipality evidence | 28 | UNRESOLVED |
| unexpected non-`CH` country representation | 10 | REVIEW / `UNEXPECTED_COUNTRY` |
| multiple plausible provider candidates | 11 | REVIEW / `MULTIPLE_PLAUSIBLE_RESULTS` |
| source-structured unambiguous coordinate | 1 | RESOLVED / MAPPABLE |
| other insufficient location evidence | 1 | UNRESOLVED |

This is upstream extraction/normalization debt. C2 does not reinterpret raw descriptions, guess a
municipality, select arbitrarily among candidates, or create a human decision. The 21 review items
are real governed uncertainty and become critical under the existing Day-0 contract.

## Causal PIT reconstruction

All target resolutions were available by `2026-08-14T14:23:10.590689Z`. The accepted downstream
cutoff is `2026-08-14T14:24:00Z`.

| Artifact | ID | Fingerprint |
|---|---|---|
| DedupRun | `2dc3b341-0be5-47b5-b726-cfa50604f86b` | `16c0b0677f7cd075e67c48f52b825f9d774939b3899679834cfed2c568e479e5` |
| PremiumSegmentRun | `d87ffba2-6a1b-4d66-803a-574d97a14580` | `bae956e2d56b756e82515b9aa83913f9e390a550717078819dc0c89f819fe7fd` |
| DashboardSnapshot | `45343909-18be-4e8e-87e9-55079d136fc1` | `04401bad3cba7b63c803135685d0fd35e74be8ff3ca71c9472684766489b7a9b` |
| Day0ReadinessAssessment | `22503245-af1d-4e75-afc3-36d891683db8` | `1e729f7379b3455c6a96b3db77185fc211c1644f8b0cb0a2a5d02546c41f3146` |

The old DashboardSnapshot `0796b785-4da6-488e-b114-674e4209b6e4`, fingerprint
`22cd7a1670427b485387ba7cbf6f0471a101c588251544cae69919abac1a6bc9`, remains unchanged with
zero mappable and 51 unmappable public-green records. The new snapshot contains one mappable and
50 unmappable records. No historical record was rewritten.

## Day-0 consequence

- required Sources: 29;
- eligible Sources: 19;
- active green vacancies: 51;
- critical green reviews: 3;
- critical geospatial reviews: 21;
- critical dedup reviews: 0;
- result: `DAY_0_BLOCKED_BY_DATA_QUALITY`;
- headline: `null`.

Geospatial evidence does not change the frozen 24/29 coverage requirement and does not manufacture
authorization.

## Replay and integrity

Exact replay reused the same 51 resolution IDs and the same four downstream artifact IDs and
fingerprints. It created no duplicate resolution, cache, RAW, review or downstream artifact and
performed zero provider requests. The source cohort, observations, lifecycle, Premium, Dedup,
Day-0, research, blocked-source, geography and Job-Room semantics were not changed.

Routine integration into daily operation remains outside C2 because
`daily-observatory-cycle-v0.1` is frozen. A later versioned operations gate may insert the governed
geospatial phase between Premium privacy classification and Dashboard materialization.

## Clean-worktree presentation correction

Browser acceptance in the clean C2 worktree exposed that the three MapLibre 6.2.0 distribution
assets used during C1 had remained in a gitignored local directory and therefore were absent from
the C1 merge. The clean page returned 404 for MapLibre CSS/ES modules. C2 includes the exact
previously exercised CSS, main module and shared module plus the upstream BSD-3-Clause license, and
removes only that vendor-directory ignore rule. Their SHA-256 values are recorded in ADR 0024.

After correction all four browser tests pass, including a real default-swisstopo failure path that
shows the bounded warning while preserving the vacancy table.

## Final validation

- full pytest suite: 482 passed in 106.90 seconds;
- focused GATE-010-C2 suite: 7 passed, including real PostgreSQL concurrent convergence;
- browser acceptance: 4 passed;
- Ruff: passed;
- mypy: passed for 161 source files;
- Django system check: passed;
- migration drift: none;
- MapLibre CSS, modules and license: found through Django staticfiles in the clean worktree;
- reference-data import on the isolated acceptance database: passed twice with identical counts;
- isolated geospatial resolution, causal PIT reconstruction and exact replay: passed;
- Source collection HTTP: zero;
- real operational database modified: no.
