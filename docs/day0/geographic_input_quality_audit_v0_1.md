# Geographic input quality audit v0.1

Date: 2026-08-25
Baseline: `99e39312535f33554a973110cba196c253628945`

## Scope

This change improves deterministic geographic normalization at collection time. It does
not change `geospatial-v0.1`, its thresholds, its provider behavior, privacy policy, or
historical evidence. It creates no migrations and performs no production mutation.

The permitted transformations are deliberately bounded:

- known Swiss country labels (`CH`, `CHE`, `Schweiz`, `Suisse`, `Svizzera`, and
  `Switzerland`) become `CH`;
- exact Swiss canton names and two-letter codes become a canton code;
- punctuation, accents, and the governed German transliterations `ae`, `oe`, and `ue`
  may be normalized for exact municipality comparison;
- ambiguous municipality names remain unresolved unless an exact governed canton
  disambiguates them;
- unknown countries and canton expressions are not silently classified as Swiss.

No fuzzy, title, description, employer, or LLM-based location matching is introduced.

## Read-only operational diagnosis

The accepted Premium target contains 51 active GREEN observations. All 51 have the
`PUBLIC_OR_NON_RESIDENTIAL` privacy context. The isolated C3 acceptance database
classifies their existing `geospatial-v0.1` evidence as:

| Outcome | Count |
| --- | ---: |
| RESOLVED | 1 |
| REVIEW | 21 |
| UNRESOLVED | 29 |

The read-only audit found two mechanically correctable input-quality classes:

- ten observations used a Swiss country label rather than the canonical `CH` code;
- the Canton Zürich adapter retained ten structured place values only as
  `raw_location`, leaving `location_locality` empty.

Other unresolved classes remain unchanged, including observations with no structured
location and geocoder responses with multiple plausible candidates.

## Implementation boundary

The common collection pipeline canonicalizes the country before constructing or
persisting a new observation. The Canton Zürich adapter promotes its already-structured
place value to `location_locality` and explicitly records canton `ZH`. Municipality
resolution first preserves the existing exact database match, then permits only a unique
match under the bounded Swiss spelling key.

Historical PostingObservations, PostingLocationResolutions, DashboardSnapshots, and PIT
artifacts are not edited or reinterpreted. Therefore the accepted historical `1 / 21 / 29`
result remains unchanged. Applying better normalization to that historical target would
require a separately governed resolver/input version and a new causal PIT chain.

## Validation

- focused geographic, required-canton, and priority-city tests: `44 passed`;
- full pytest against isolated PostgreSQL 16: `550 passed`;
- Ruff: pass;
- mypy: pass, 169 source files including `manage.py`;
- Django check: pass;
- migration drift: none;
- production database writes: `0`;
- Source HTTP requests: `0`;
- geocoder/provider HTTP requests: `0`.
