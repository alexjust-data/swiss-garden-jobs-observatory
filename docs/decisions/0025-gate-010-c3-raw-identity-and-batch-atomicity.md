# ADR 0025: GATE-010-C3 RAW identity and geospatial batch atomicity

## Status

Accepted for implementation; isolated operational acceptance and independent audit pending.

## Context

Merged GATE-010-C2 baseline:
`8743d1d3c4a25fb9f22f79576f960851c661769c`.

Frozen correction contract:
`docs/day0/gate_010_c3_raw_identity_atomicity_contract_v0_1.md`, committed alone as
`0279178cf2e2bf82ba6006d52ba652d1c0b3ad18`.

The first post-merge C2 application encountered an exact content-addressed geocoder file produced
by the isolated acceptance database but absent from the operational database's metadata. The
strict filesystem create rejected that existing final key. Twelve earlier targets had already
committed because batch atomicity was only per target.

## Decision

RAW publication is atomic, no-overwrite and content-idempotent. A same final key with identical
complete bytes is reusable storage; a same key with different bytes is a conflict. File presence
never transfers database authority. Local RAW and cache rows are created or reused only after
complete current-execution identity validation.

Mutable non-operational databases may not use the production default RAW root. Tests may inject a
temporary store directly; operational-copy acceptance must configure an explicit isolated root.

After complete C2 target and existing-resolution preflight, every live
`resolve_premium_locations` invocation places all new RAW metadata, cache rows, resolutions and
review items in one outer database transaction. Nested per-target transactions are savepoints.
Any target failure rolls back every new database row from that invocation. Immutable final-key
bytes already published are retained and have no scientific authority until independently
registered by a successful database transaction.

## Incident evidence

The twelve already-committed operational resolutions and one review item remain immutable. No
restoration, deletion or retrospective transaction is manufactured. The failed attempt built no
downstream PIT and performed no Source HTTP.

The verified pre-execution backup has SHA-256
`a5f4d4c463c51db8299ef771cf047ecb4efa20aab064e8f95fae4894794d18b6`.
The incident request and response identities are recorded in the incident document and frozen C3
contract.

## Consequences

Exact retry after C3 merge can reuse the twelve incident rows, independently reconcile the exact
orphan bytes into operational metadata and resolve only the remaining targets. A second exact
retry must use no provider requests and must reuse all IDs.

The correction changes no geospatial classification, privacy, public coordinate, marker,
Premium, Dashboard, Day-0, Source or lifecycle semantics. No migration is required.

## Acceptance boundary

Before independent audit, recovery runs only on a copy of the postincident operational database
with an explicit isolated RAW root. The real operational database receives no additional C3
writes. A successful isolated batch is followed by exact retry and a new causal downstream PIT
replay.

## Accepted isolated result

The postincident copy began with the preserved twelve incident rows. The final batch reused those
twelve, created the remaining 39 atomically, safely registered the exact orphan response in the
local database and reproduced the accepted 1/21/29 scientific result. Exact retry used zero
provider requests.

The new causal cutoff is 2026-08-14T17:33:00Z. Its aligned Dedup, Premium, Dashboard and Readiness
IDs are respectively f9c92adf-3547-48d8-8b95-b569f40b9d42,
76ece3d2-46c6-41a2-ba9e-da0467c37de4, a33ce5aa-45bb-4c0e-8bf3-82bef07dd92d and
c75f0e1d-f9df-4b89-89f7-0eea7b7dc3c7. Exact replay reused all four.

Acceptance also established the platform implementation: Windows uses same-volume atomic
no-overwrite os.rename, while POSIX uses atomic hard-link publication. Both use an fsynced
same-directory temporary with a short bounded name.

Windows-invalid logical filename components are mapped to a collision-free physical name under a
reserved ~raw~ prefix. The database object_key remains unchanged. A literal percent sequence
cannot collide with an escaped colon, and legacy Windows paths remain readable.
