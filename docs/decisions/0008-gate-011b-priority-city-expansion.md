# Decision 0008: GATE-011B priority city expansion

## Status

Authorized for implementation in GATE-011B.

## Authorized batch

Exactly these four frozen source identities are in scope:

- `SRC-OFF-CITY-BERN`
- `SRC-OFF-CITY-LUZERN`
- `SRC-OFF-CITY-STGALLEN`
- `SRC-OFF-CITY-SCHAFFHAUSEN`

They complete the six-city Day-0 municipal target layer after the already implemented Zurich and Winterthur sources. No substitute or additional source is authorized.

## Architecture

Platform adapters remain pure translators into `ListingEntry`, `ListingPage`, and `ParsedSourcePosting`. Governed HTTP, immutable RAW/SHA-256 evidence, the shared observation contract builder and validator, Posting identity, lifecycle, green relevance, source health, and FULL_SOURCE completeness remain owned by `SharedCollectionPipeline`.

Bern and Luzern are verified Prospective deployments with materially different listing contracts: Bern exposes the current public v1 JSON API, while Luzern uses the legacy Prospective HTML career center with form pagination. They share common Prospective detail translation but retain separate discovery implementations.

Schaffhausen is a city-owned WordPress presentation layer linked to Umantis. Active listing pages and local mirrored details are authoritative collection surfaces. The external Umantis origin is not authorized or fetched; externally linked listing rows must resolve to the exact city-owned mirror or fail closed.

St. Gallen currently exposes an Abacus AbaShop deployment whose `robots.txt` disallows `/`. It is `ACCEPTED_BLOCKED`: no adapter, endpoint authorization, or automated request is created. The source remains in the Day-0 required denominator.

## Day-0

GATE-011B does not select a numeric completion threshold or a maximum FULL_SOURCE age. Both authorization-policy dimensions remain pending. Source expansion cannot authorize a Day-0 market figure.

The frozen `docs/research/v0_4/` package and all closed-gate scientific semantics remain authoritative, read-only, and unchanged.
## Schaffhausen detail governance

Where a city listing points to Umantis, the unauthorized Umantis origin is not fetched. Stable
vacancy identity is resolved through the city-owned WordPress index and the city-owned REST
record supplies the conservative source detail. Missing fields remain unknown; no external detail
is inferred.