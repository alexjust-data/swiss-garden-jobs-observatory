# Decision 0003: GATE-007 Incremental Platform Reuse

## Status

Accepted for GATE-007.

## Decision

GATE-007 proves the reusable platform architecture with:

1. the existing REXX/Winterthur source migrated onto the shared platform pipeline; and
2. one second canonical municipal source using a different, technically verified platform family.

The second source is `SRC-OFF-CITY-ZURICH`. It is a frozen P0 canonical municipal source recorded as `CITY_SITE_SUCCESSFACTORS_LINKED`. Live reconnaissance confirmed that the official city portal uses a Stadt Zurich AEM search API and city-owned detail pages linked to SAP SuccessFactors requisitions. This is consistent with the frozen platform-family description.

Adapters describe platform-specific discovery and parsing. Governed HTTP, RAW preservation, contract validation, observations, posting identity, lifecycle, green relevance, source health, and snapshot completeness remain shared scientific services.

Umantis, Solique, Prospective, and additional platform families remain deferred. Platform mismatches must stop implementation rather than silently alter the frozen registry.

The frozen `docs/research/v0_4/` package remains authoritative, read-only, and unchanged. This incremental sequencing decision does not weaken any frozen technical contract.
