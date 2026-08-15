# GATE-010-C4 — Operational RAW lineage consolidation contract v0.1

Status: FROZEN BEFORE C4 IMPLEMENTATION OR ACCEPTANCE

Baseline: merged GATE-010-C3 `0a6dc823b4716cbaea1cf5f3418881ed79410d33`.

## Purpose

The post-merge C3 production preflight found that the operational PostgreSQL database references
one coherent set of immutable RAW identities, but the corresponding physical bytes are split
across historical local roots. The configured operational root is relative to the current
worktree and contains no object referenced by the operational database. A further historical
Windows representation uses U+F022 in physical filenames where the logical object key contains a
colon; merged C3 does not recognize that representation.

C4 governs physical RAW lineage, verified replication and operational-root designation only. It
does not change a RawArtifact row, logical object key, payload byte, Posting, Observation,
CollectionRun, lifecycle event, geospatial result, privacy rule, Dedup, Premium, Dashboard,
Day-0 policy or operational cycle.

## Established preflight evidence

The operational database is `swiss_garden_jobs` and contains 10,917 RawArtifact rows. The initial
read-only inventory found:

- 5,811 database identities in one historical root;
- 5,106 database identities in another historical root;
- no database identity in the configured worktree-relative root;
- no missing database identity across the two historical roots;
- no identity present in more than one physical object;
- 10,737 identities under current or previously governed Windows mappings;
- 180 identities under an additional exact U+F022 representation;
- all 180 U+F022 objects equal their RawArtifact byte size and SHA-256;
- the 51 accepted Premium target observations in the first historical root;
- the three current geocoder cache RAW objects in the second historical root.

These observations establish the incident and motivate C4. They are not permission to copy or
rewrite evidence before this contract is frozen. C4 acceptance must independently reproduce the
complete inventory and every digest.

## Governing identities

A governed RAW identity remains:

```text
validated logical object_key
+
complete immutable bytes
+
SHA-256
+
byte size
```

`RawArtifact.object_key` is the logical identity. A physical filename representation, filesystem
root or worktree path is not scientific identity and cannot alter the logical key.

An operational RAW lineage is one explicitly designated absolute root plus an immutable manifest
that proves which physical object satisfies every RawArtifact row in the operational database.

## Source-root boundary

Historical source roots are evidence sources and are read-only during C4.

Forbidden source-root operations:

- rename, move, delete, overwrite or normalize historical files;
- create metadata inside a historical root;
- choose a source merely because its filename is similar;
- use case-insensitive lookup as proof of logical ownership;
- import a whole foreign database or alter RawArtifact rows to make files fit.

Inventory uses exact component spelling. Symlinks, paths escaping a declared root and ambiguous
physical ownership fail closed.

## Recognized physical representations

C4 may recognize only predeclared deterministic representations:

1. the current C3 injective Windows physical representation;
2. the exact pre-correction C3 percent-encoded legacy representation;
3. an exact direct representation where already permitted by C3;
4. the observed historical representation obtained by replacing each logical colon (`:`) with
   U+F022 in the same component, with every other character unchanged.

The U+F022 rule is compatibility evidence only. It does not redefine the canonical writer and is
not generalized to other private-use characters or forbidden characters without a future gate.

For each RawArtifact row, C4 resolves all candidate source paths across every declared source
root using exact spelling. Required classification:

- `PRESENT_EXACTLY_ONCE`: one candidate whose bytes, SHA-256 and size match;
- `MISSING`: no exact candidate;
- `AMBIGUOUS`: more than one distinct physical candidate;
- `CONFLICTING`: candidate bytes, size or SHA-256 differ from PostgreSQL authority;
- `UNSAFE`: path traversal, symlink, unsupported representation or unreadable evidence.

Only `PRESENT_EXACTLY_ONCE` is importable. Every other classification stops before destination
mutation.

## Coherent source snapshot and manifest

The source inventory is captured read-only against one coherent PostgreSQL snapshot. The manifest
version is `operational-raw-lineage-v0.1`.

The canonical manifest records, at minimum:

- manifest and format versions;
- sanitized database identity and PostgreSQL snapshot identifier;
- export transaction start in normalized UTC;
- merged C3 baseline SHA;
- Django migration inventory;
- every RawArtifact primary key, logical object key, SHA-256, byte size and content type;
- sanitized source-root labels, never credentials;
- exact physical representation class and source-relative path for each identity;
- per-row canonical SHA-256;
- counts by source root and representation;
- missing, ambiguous, conflicting and unsafe counts;
- canonical manifest SHA-256.

Absolute machine paths are runtime evidence and are not committed as normative policy. A
sanitized designation committed after isolated acceptance pins the manifest version, manifest
SHA-256, database snapshot fingerprint, source inventory fingerprint, expected object count,
expected aggregate byte count and merged governance SHA.

The importer independently recomputes the manifest, row hashes, counts and package fingerprint.
It does not trust self-reported manifest values.

## Canonical operational root

The destination is a new, explicitly configured, absolute path outside any Git worktree. It must
be distinct from every historical source root and from every isolated acceptance root.

Before mutable use, the root contains an immutable lineage designation sentinel binding:

- lineage version;
- accepted manifest SHA-256;
- database snapshot fingerprint;
- object count and aggregate byte count;
- created-at/replicated-at in normalized UTC;
- merged C4 governance evidence after merge where applicable.

The application must reject an operational database mutable run when:

- the configured execution root is relative;
- the configured operational root is relative;
- execution and operational roots differ;
- the designation sentinel is absent, malformed or conflicting;
- the sentinel does not bind the audited lineage expected by configuration;
- the configured root is a worktree-local default.

Tests and isolated databases use separately designated temporary roots. A test root never becomes
operational authority.

## Destination publication

Consolidation writes every logical key through the current C3 RawObjectStore mapping and atomic
no-overwrite publication.

For each preflight-approved identity:

1. read the exact source bytes;
2. independently recompute size and SHA-256;
3. derive the current canonical destination path from the unchanged logical object key;
4. atomically publish or exactly reuse complete bytes;
5. read the destination through RawObjectStore;
6. independently recheck size and SHA-256;
7. record the replication result in bounded acceptance evidence.

Existing identical destination bytes are reused. Existing conflicting or ambiguously owned bytes
fail closed. No destination object is overwritten, truncated, appended, renamed or deleted.

The source filesystem may remain unchanged after successful consolidation. Historical files do
not become redundant evidence eligible for deletion in C4.

## Transaction and interruption semantics

Filesystem replication cannot be one PostgreSQL transaction. C4 therefore uses deterministic,
per-object atomic publication plus a final authority boundary:

- an interrupted run may leave verified destination objects without a designation sentinel;
- such bytes are not yet the operational root authority;
- exact retry reuses them only after re-verification;
- the designation sentinel is atomically published last, only after all expected identities pass;
- a failed run never publishes a successful designation;
- a conflicting pre-existing sentinel fails closed.

No RawArtifact or scientific row is created, updated or deleted by consolidation.

## Backup and restore

Before real consolidation, create and verify:

- a PostgreSQL custom-format backup of the operational database;
- a complete immutable backup/snapshot of each declared historical source root;
- a source inventory manifest and SHA-256 evidence for every database-referenced object.

Backup credentials and DSNs are not recorded. Backup acceptance records timestamps, bounded
artifact paths, sizes, SHA-256 or inventory fingerprint and restore instructions.

Restore acceptance uses an isolated database and isolated RAW root. It must read every restored
RawArtifact by logical key and reproduce all 10,917 SHA-256 and size values without Source or
geocoder HTTP.

## Dry-run, apply and replay

Dry-run performs the complete PostgreSQL/source/destination preflight and writes nothing.

The first isolated apply must produce:

- all expected logical identities in the canonical root;
- zero missing, ambiguous, conflicting or unsafe identities;
- zero database mutations;
- one final designation sentinel.

The exact second apply must reuse every destination object, create zero objects, mutate zero
objects and reuse the exact designation identity.

Changing source bytes, database identity, manifest or designation under the same lineage version
fails closed.

## Production resumption boundary

Only after C4 implementation, isolated acceptance, independent audit and merge may the real
operational root be consolidated and designated.

Then, and only then:

1. configure both execution and operational RAW settings to the designated absolute root;
2. verify all RawArtifact rows through the application read API;
3. run the exact governed geospatial retry;
4. require reuse of the twelve preserved incident resolutions and completion of the remaining
   target resolutions under C3 batch atomicity;
5. run a second exact retry and require zero provider calls;
6. construct a new causally valid Dedup/Premium/Dashboard/Readiness PIT;
7. preserve all historical PIT and incident evidence.

C4 itself performs no Source collection and no geocoder acquisition before merge.

## STOP conditions

C4 stops before destination authority or real operational retry if:

- any RawArtifact identity is missing, ambiguous, conflicting or unsafe;
- exact U+F022 ownership cannot be proven;
- any source or destination byte fails SHA-256 or size validation;
- the destination is within a worktree or equals a source/isolated root;
- an existing destination object or designation conflicts;
- the complete source snapshot cannot be backed up and restored;
- application reads cannot reproduce every database identity;
- consolidation would require a RawArtifact or scientific-history mutation;
- another frozen scientific contract would need semantic change.

## Integrity

C4 introduces:

- no Source HTTP;
- no geocoder HTTP before post-merge production resumption;
- no human adjudication;
- no RawArtifact mutation;
- no historical source-file mutation;
- no geospatial, privacy, marker, Dedup, Premium, Dashboard or Day-0 semantic change;
- no synthetic evidence;
- no deletion or destructive retention.

The governing invariant is:

```text
one PostgreSQL RAW identity
        → exactly one verified object in one designated operational root

historical physical representation
        → compatibility input only

canonical operational authority
        → current injective mapping + exact bytes + immutable manifest designation
```
