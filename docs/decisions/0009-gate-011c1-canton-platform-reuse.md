# Decision 0009: GATE-011C-1 canton platform reuse

## Status

Authorized for implementation. This decision does not authorize Day-0.

## Scope

Exactly four required P0 source identities are in scope:

- `SRC-OFF-CANTON-ZH`
- `SRC-OFF-CANTON-AR`
- `SRC-OFF-CANTON-ZG`
- `SRC-OFF-CANTON-BL`

## Decision

Live reconnaissance verified two vendor families with distinct deploy-time contracts:

- Zurich uses the modern Solique JSON API; Appenzell Ausserrhoden uses the legacy Solique client-side JSON feed.
- Zug and Basel-Landschaft use configurable Prospective legacy listings with POST pagination and official JSON-LD detail pages.

Adapters are selected by exact source identity before platform family. This prevents a verified adapter from silently enabling another source that happens to carry the same registry platform label.

Platform code translates listing/detail evidence into the common DTOs. HTTP governance, RAW/SHA storage, observation contracts, lifecycle, green relevance, source health and completeness remain in the shared collection pipeline.

## Access and origins

Automation still requires the existing explicit acknowledgement. Only origins verified in the GATE-011C-1 reconnaissance are registered. Basel-Landschaft Umantis links are not authorized network origins.

## Completeness

Solique feeds are complete in-memory job universes. Zurich additionally exposes a reported position count, which must equal unique discovered IDs. Prospective listings exhaust deterministic POST offsets; Basel-Landschaft also reports a total that must equal unique IDs. A conflict, malformed payload, non-advancing page or mismatched total fails closed and cannot produce a healthy complete snapshot.

## Geography and dates

Canton employer identity is not location evidence. Free-text location is retained, but municipality remains unknown unless the source explicitly supplies governed locality evidence. Update timestamps are not publication timestamps. Missing publication evidence remains missing.

## Day-0

The numeric completion threshold and maximum FULL_SOURCE age remain pending. GATE-011C-1 can increase required-source evidence but cannot authorize a market figure.

## Exclusions

No new source outside the four identities, no dedup/premium/dashboard semantic change, no scheduler, no geocoding, and no threshold or freshness policy.
