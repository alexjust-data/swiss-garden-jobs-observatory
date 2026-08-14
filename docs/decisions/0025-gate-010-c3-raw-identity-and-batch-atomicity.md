# ADR 0025: GATE-010-C3 RAW identity and geospatial batch atomicity

## Status

Implementation and independent-audit correction complete; final independent audit pending.

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

The actual operational RAW root is explicitly designated independently from the mutable execution
root. Every mutable batch validates the effective store, including injected resolvers.
Non-operational databases may use only an explicitly distinct root; sharing the designated
operational root fails before provider activity or evidence mutation.

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

Windows physical names use a compact lower-case ASCII representation that is injective under
case-insensitive filename semantics. Canonical lower-case components remain compact; components
that could alias are represented under a reserved ~raw~ prefix with delimited UTF-8 hex escapes.
The database object key remains unchanged, backslash is rejected as a second separator, and
legacy Windows paths remain readable.

## Independent-audit correction

At audited head 10f4732d4b9a3b6d48d36f46e4f894d5089e6ab2, independent review found that
the initial conditional Windows mapping did not distinguish all case pairs, custom operational
roots and injected resolvers were not fully bound to RAW lineage, and cache validation trusted a
safe-but-not-deterministic requested URL and mutually consistent unaccepted content types.

The final implementation closes those paths without changing geospatial-v0.1 or the historical
incident. Cache and fetched-response acceptance now independently bind exact request URL, final
same-origin URL, status, accepted content type, bytes, SHA, size and parsed payload. The existing
isolated 51-resolution corpus and all four downstream PIT artifacts replay exactly with zero
provider requests. No real operational evidence was modified.
