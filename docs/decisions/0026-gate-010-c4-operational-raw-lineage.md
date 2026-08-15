# ADR 0026: GATE-010-C4 operational RAW lineage consolidation

## Status

Implementation and isolated acceptance complete; independent audit pending.

## Context

Merged C3 baseline: `0a6dc823b4716cbaea1cf5f3418881ed79410d33`.

Frozen C4 contract commit: `2f092daf77c8e5131226fcd793a77ca9d6d38212`.

Post-merge production preflight found that the operational database's 10,917 immutable RAW
identities were physically split across two historical roots. The configured worktree-relative
root represented none of them. A further 180 identities used a historical U+F022 physical
representation for logical colon characters that merged C3 did not recognize.

The evidence was complete and non-conflicting; the defect was physical lineage and operational
designation, not missing scientific evidence.

## Decision

C4 introduces one canonical `operational-raw-lineage-v0.1` manifest. It binds a coherent
PostgreSQL snapshot, the complete RawArtifact inventory, exact source-root/physical
representations, per-row fingerprints, migration inventory and governance SHA.

Historical roots remain read-only. C4 recognizes only current C3 names, the pre-correction C3
legacy mapping, exact direct names and the observed colon-to-U+F022 compatibility mapping. Exact
component spelling is mandatory. Missing, ambiguous, conflicting, unsafe or digest-mismatched
evidence fails before destination mutation.

Consolidation publishes the unchanged logical object key through the current C3 injective writer
into a new absolute root outside Git worktrees. Each object uses atomic no-overwrite publication
and immediate byte/size/SHA verification. PostgreSQL RawArtifact rows are not copied, updated or
deleted.

The destination becomes operational authority only when an immutable designation sentinel is
published last. Interrupted runs without a sentinel may be retried idempotently. A root already
sealed by a sentinel must be complete and cannot be repaired silently.

Operational geospatial execution now requires an absolute execution root, an identical absolute
operational root, the committed manifest SHA configuration and a matching sentinel. A relative
worktree root cannot become production authority.

## Acceptance

The audited manifest contains 10,917 objects / 548,577,481 bytes, with 10,737 current C3 and 180
U+F022 representations. Its SHA-256 is
`92e1e888277db9e25e4a91929c34917fb972f9d86b07ce97412212f6c504c900`.

PostgreSQL and both historical roots were backed up. The dump SHA-256 is
`953b6da8481ab04ff9e894562ab5d4e208bba28936f5a8970c4acfcbc2f3c27d`. An isolated database restore
and restored RAW snapshots reproduced the exact RawArtifact and source inventory fingerprints.

An isolated external canonical root converged to all 10,917 identities and the exact designation
sentinel. Exact replay created zero objects and reused all 10,917. The restored operational dry-run
selected the same 51 geospatial targets, found the preserved twelve incident rows and performed
zero provider requests.

## Consequences

C4 adds no migration and changes no scientific semantics. It adds two management commands:

- `build_raw_lineage_manifest` for read-only candidate capture;
- `consolidate_operational_raw_lineage` for repository-designated dry-run/apply.

The manifest payload remains an external audited artifact; only its bounded designation is
committed. Source roots and backups are not deleted after consolidation.

After independent audit and merge, operations must back up again or revalidate the accepted
backup, apply the exact manifest to the new real canonical root, configure its absolute path and
manifest SHA, verify all database RAW identities and only then resume the C3 geospatial retry and
new causal PIT construction.
