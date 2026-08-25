# GATE-010-C5 — governed geospatial resolution v0.2 contract

Contract version: `gate-010-c5-geospatial-v0.2-contract-v0.1`

Authoritative merged baseline: `99e39312535f33554a973110cba196c253628945`
Stacked geographic-input base: `2c92cf6dc03c0cb49914319b045b51856d0cd3e6`

## 1. Purpose and boundary

C5 introduces a new resolver identity, `geospatial-v0.2`, for bounded exact Swiss
municipality resolution. It implements the frozen geographic priority:

```text
BFS municipality identity
    ↓
municipality + canton
    ↓
postcode + municipality
    ↓
regional text
    ↓
review
```

It does not alter `geospatial-v0.1`, privacy policy `location-privacy-v0.1`, Premium,
Dashboard, Day-0, or historical artifacts. Existing v0.1 rows and review items remain
immutable and retain their original interpretation.

## 2. No historical rewrite

Forbidden:

- update, delete, retarget, or reinterpret a v0.1 location resolution;
- mutate a PostingObservation to make v0.2 resolve;
- modify a historical DashboardSnapshot or PIT artifact;
- replace a v0.1 review item with a v0.2 result;
- promote uncertain evidence merely to increase marker count.

V0.2 creates new append-only evidence under a distinct resolver version. Any downstream
visibility requires a new causal PIT cutoff after the v0.2 evidence exists.

## 3. Governed input identity

The v0.2 input fingerprint binds every field capable of changing its result, including:

- resolver and privacy-policy versions;
- PostingObservation, Source, and privacy-context identities;
- existing Municipality BFS/name/canton identity, when present;
- street, postcode, locality, region, country, and structured source coordinates;
- bounded raw-location evidence when section 5 permits it;
- source format and the governed source canton identity used by section 5.

Two rows with the same observation, resolver, and privacy context but different input
fingerprints are a conflict and fail closed. Identical input reuses the exact row.

## 4. Bounded Swiss label normalization

Only finite, tested aliases may normalize to Switzerland (`CH`):

```text
CH, CHE, Schweiz, Suisse, Svizzera, Switzerland
```

Unknown or foreign labels never become `CH`. Canton normalization accepts only the 26
Swiss codes and bounded official-language canton names. Municipality comparison permits
only punctuation/accent normalization and the governed German transliterations
`ae/oe/ue`. It is not fuzzy matching.

## 5. Municipality identity derivation

V0.2 may establish the municipality only through the first unique applicable rule:

1. reuse the observation's exact Municipality FK;
2. resolve an exact normalized `location_locality` within an exact governed canton;
3. when locality is empty, use the complete `raw_location` only if all of these hold:
   - privacy context is `PUBLIC_OR_NON_RESIDENTIAL`;
   - street and postcode are empty;
   - the source is an official canton Source whose governed ID encodes one valid canton;
   - the structured source format explicitly identifies the field as a place value;
   - the complete value resolves to exactly one Municipality in that canton.

Rule 3 initially permits only the already-governed Canton Zürich Solique representation
(`SRC-OFF-CANTON-ZH`, `SOLIQUE_KTZH_API_V1`). Generalizing it requires new evidence and
tests; it must not happen through loose source-name or coverage-scope parsing.

If a rule yields zero or more than one Municipality, it does not establish identity.
Title, description, employer, arbitrary raw text, similarity, and LLM inference are
forbidden inputs.

## 6. Municipality-only SearchServer requests

When the best governed precision is Municipality, the request is exactly:

```text
searchText = canonical municipality name + canton code
origins = gg25
geometryFormat = geojson
lang = de
limit = 10
sr = 4326
type = locations
```

The request must be a pure projection of fingerprinted material. Street/address results
are never selected for municipality-only evidence.

The existing v0.1 street/postcode priority remains unchanged when those structured fields
are available and privacy permits them.

## 7. Candidate acceptance

A municipality-only result is `RESOLVED` only if:

- provider and response provenance pass the existing C2/C3 validation;
- the candidate is a `gg25` municipality candidate;
- its normalized municipality identity agrees with the exact governed Municipality;
- it is Swiss and does not contradict the governed canton;
- all accepted matches converge to exactly one coordinate pair.

Otherwise the result is `REVIEW` or `UNRESOLVED` with bounded evidence. An address,
district, gazetteer, or multiple coordinate result cannot win merely by rank.

Accepted municipality-only coordinates use:

```text
location_precision = MUNICIPALITY
coordinate_source = SWISSTOPO_SEARCHSERVER
privacy_display_level = MUNICIPALITY_CENTROID
```

## 8. Privacy

`PRIVATE_RESIDENCE` and `CONFIDENTIAL_PRIVATE_RESIDENCE` continue to use only the governed
Municipality/canton request and keep public-display coordinates hidden. V0.2 must not add
raw locality, street, postcode, address, description, or employer text to protected
requests, fingerprints exposed publicly, review evidence, logs, or Google links.

The protected-request adversarial matrix from C2 remains mandatory.

## 9. Batch and storage guarantees

V0.2 retains C2/C3 guarantees:

- all-target conflict preflight before provider or mutation;
- one outer database transaction for the batch;
- atomic immutable RAW publication;
- exact cache provenance validation;
- actual operational RAW-root isolation;
- concurrent identical convergence;
- any provider, RAW, cache, metadata, or identity conflict rolls back all new database
  evidence in the batch.

## 10. Acceptance target

Acceptance uses an isolated copy and the exact C3 Premium target:

```text
PremiumRun: 76ece3d2-46c6-41a2-ba9e-da0467c37de4
GREEN_CONFIRMED: 51
```

The v0.1 historical result remains:

```text
RESOLVED: 1
REVIEW: 21
UNRESOLVED: 29
```

C5 does not predeclare a desired v0.2 marker count. Evidence decides. It must report each
transition class, municipality derivation rule, provider/cache count, and unresolved or
review reason.

Source collection HTTP is zero. Bounded geo.admin provider requests are allowed only
against an isolated target after preflight. The real operational database and RAW lineage
remain untouched before independent audit and merge.

## 11. Replay and PIT

The exact second v0.2 execution must reuse all v0.2 resolutions and make zero provider
requests. A new isolated causal chain may then be built:

```text
Dedup → Premium → Dashboard → Readiness
```

The new Dashboard may expose only validated public-display coordinates. Historical
snapshots and the C3 PIT chain remain unchanged.

## 12. STOP conditions

Stop before target mutation when:

- municipality identity is conflicting or ambiguous;
- a v0.2 governed identity exists with another input fingerprint;
- protected input would require a raw-field fallback;
- request, response, RAW, cache, or root-lineage provenance fails;
- a result would require fuzzy/textual inference or human adjudication;
- validation would require Source recollection;
- the real operational database would need a pre-merge write.

## 13. Validation

At minimum prove:

- all normalization and municipality-derivation rules, including ambiguity;
- exact municipality-only `gg25` request construction;
- non-gg25 and multiple-coordinate candidates fail closed;
- country aliases and foreign-country refusal;
- protected privacy canaries;
- batch preflight, rollback, cache, RAW, and concurrency regressions;
- v0.1 historical rows/API/snapshot immutability;
- exact v0.2 retry with zero provider requests;
- new isolated PIT and exact replay;
- Ruff, mypy, Django check, migration drift, full pytest, browser, CI, GitGuardian, and
  zero unresolved review threads.

No schema migration is expected. If implementation proves one is required, stop and
amend the design through an independently audited contract correction before creating it.
