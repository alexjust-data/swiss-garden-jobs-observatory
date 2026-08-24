# GATE-010-C4 — Operational RAW lineage acceptance audit v0.1

Status: IMPLEMENTATION READY FOR INDEPENDENT AUDIT

## Governance

- baseline: `0a6dc823b4716cbaea1cf5f3418881ed79410d33`;
- contract-only commit: `2f092daf77c8e5131226fcd793a77ca9d6d38212`;
- lineage version: `operational-raw-lineage-v0.1`;
- frozen research changes: zero;
- migrations: none.

The frozen contract remains absent from every implementation diff after its isolated commit.

## Independent-audit correction

Prior audited head: `994c4734c6809bd0a785daf990c3af604fb7dda4`.

The independent audit found three enforcement gaps:

1. the accepted manifest described successful representations but did not explicitly bind all
   five frozen identity-classification counts;
2. runtime consolidation rejected an equal source/destination and a destination in a Git
   worktree, but did not reject both directions of source/destination nesting;
3. the operational runtime sentinel validator did not independently reject a designated root
   inside a Git worktree.

The correction adds the complete classification vector to the manifest, snapshot fingerprint,
verification and command output; rejects equal and bidirectionally nested roots before provider
or destination mutation; and rejects worktree-local operational roots in the runtime authority
validator itself. The original manifest remains immutable external historical evidence. The
governed manifest command recaptured a new corrected manifest and designation without changing
any RawArtifact row, source bytes, inventory fingerprint or scientific contract.

## Post-merge incident reconstruction

The operational database `swiss_garden_jobs` contains 10,917 unique RawArtifact rows. The
worktree-relative configured root contained nine physical files and zero database-referenced
identities. Exact read-only inventory reconstructed every database identity across two historical
roots:

| Evidence source | Database identities | Physical files | Physical bytes |
|---|---:|---:|---:|
| historical gate011f root | 5,811 | 10,223 | 505,673,765 |
| historical repository root | 5,106 | 5,394 | 280,233,748 |
| configured worktree root | 0 | 9 | 36,047 |

No database identity occurred in both historical roots. No database identity was missing.

Current/previous C3 filename representations accounted for 10,737 identities. A further 180
identities used exact U+F022 physical filenames for logical colon components. Every one of those
180 objects independently reproduced its PostgreSQL byte size and SHA-256. Merged C3 could not
read a representative U+F022 key through RawObjectStore, proving the compatibility defect rather
than a missing-payload incident.

The 51 Premium target observation RAW objects reside in the first historical root. The three
GeocoderCacheEntry RAW objects reside in the second. Therefore neither root alone could be the
operational lineage.

## Audited manifest and designation

One PostgreSQL `REPEATABLE READ / READ ONLY` snapshot produced:

- manifest SHA-256:
  `4ae6d26bba0564a1222261e4b29cde8129c740de115267a5a34e5c9c1c7ed0b1`;
- database snapshot fingerprint:
  `36f50c1d578df2a2c5c9a7920e215b56149614e26424765b75401d6c218da402`;
- RawArtifact inventory fingerprint:
  `4e06ee520ef5810e5e3427efd3f18795430a2d264d74f8481034a168800e4c4a`;
- source inventory fingerprint:
  `6ec5336a8a0bc03ef078c5864223ce8fce54f3f8cd80ae1f50505fac94b5c9d0`;
- object count: 10,917;
- aggregate governed bytes: 548,577,481;
- `CURRENT_C3`: 10,737;
- `LEGACY_U_F022_COLON`: 180;
- `PRESENT_EXACTLY_ONCE`: 10,917;
- `MISSING`: 0;
- `AMBIGUOUS`: 0;
- `CONFLICTING`: 0;
- `UNSAFE`: 0.

The committed sanitized designation pins these values and the isolated contract commit. The
authoritative consolidation command has no runtime designation override.

The pre-correction manifest SHA
`92e1e888277db9e25e4a91929c34917fb972f9d86b07ce97412212f6c504c900` and snapshot fingerprint
`5f26ab13a39956bbcab386f9c211d54607a4899c316c6dd02a63c61ab8d667e6` remain preserved as
under-bound historical audit evidence and are not accepted by the corrected verifier.

## Backup and restore

Before isolated consolidation, the real operational database and both complete historical roots
were backed up outside the repository.

PostgreSQL custom-format backup:

- bytes: 140,484,741;
- SHA-256:
  `953b6da8481ab04ff9e894562ab5d4e208bba28936f5a8970c4acfcbc2f3c27d`.

The RAW backups are complete directory snapshots. `robocopy /L /MIR` returned zero for both after
copy. The first snapshot contains 10,223 files / 505,673,765 bytes; the second contains 5,394 files
/ 280,233,748 bytes.

The database restored into isolated PostgreSQL database
`swiss_garden_jobs_gate010c4_restore_20260815`. Rebuilding the manifest from the backup RAW
snapshots reproduced exactly:

- object count: 10,917;
- aggregate bytes: 548,577,481;
- RawArtifact fingerprint:
  `4e06ee520ef5810e5e3427efd3f18795430a2d264d74f8481034a168800e4c4a`;
- source inventory fingerprint:
  `6ec5336a8a0bc03ef078c5864223ce8fce54f3f8cd80ae1f50505fac94b5c9d0`;
- representation counts: 10,737 current + 180 U+F022.

The restored snapshot/manifest SHA differs, as required, because PostgreSQL snapshot identity and
physical root identities are new.

The original operational, restored and corrected manifests are retained with the external C4
backup. Their physical file SHA-256 values are:

- operational manifest file:
  `e779fd07542a69476fce04fed220c195bd6fc2afdcaaf9861d435ebd28fcf888`;
- restored manifest file:
  `47d62d0d3c94618316caf0b8b2a57b22675f4f96c91ef79f1da7960faf01920f`;
- corrected operational manifest file:
  `9a7432e043f5d9b7b90d507ebad29be44cda40d1fe1239613df5b18ad783586a`.

## Isolated consolidation

The complete dry-run targeted a nonexistent external root and returned:

```text
selected          10917
created               0
reused                0
sentinel created  false
destination exists false
```

The first isolated apply started with a nonexistent external root. It atomically published and
verified all 10,917 objects and then published the designation sentinel. The command wrapper
timed out while performing a second, redundant full-corpus audit after the sentinel. Inspection
proved the terminal state already contained exactly 10,917 governed objects / 548,577,481 bytes
and the exact designation sentinel.

The implementation was then simplified without weakening evidence: destination preflight verifies
every pre-existing object; every newly published object is immediately read and verified; the
sentinel is published last. The duplicate post-sentinel read was removed. A sealed root missing an
object now fails closed rather than repairing itself.

Exact second apply against the isolated restored database returned:

```text
selected          10917
created               0
reused            10917
sentinel created  false
sentinel reused    true
```

The sentinel replication time is `2026-08-15T10:11:57.243579Z` and pins the exact audited
designation.

After the audit correction, the complete read-only production preflight revalidated the same
10,917 identities / 548,577,481 bytes against both historical roots and the corrected
designation. It returned `created=0`, `dry_run=true`, published no sentinel and did not create
the external destination. No Source or geocoder HTTP was performed.

## Operational guard

Using the restored database as the designated operational database and the isolated canonical RAW
root, `resolve_premium_locations --dry-run` passed the new authority guard and returned:

- selected: 51;
- already present: 12;
- created: 0;
- provider requests: 0.

Mutable execution against the operational database now requires:

- absolute execution root;
- absolute operational root;
- identical effective roots;
- repository-designated manifest SHA-256;
- a matching immutable root sentinel.

Non-operational isolated roots retain C3 separation semantics.

## Real production boundary

The real operational database remains unchanged:

- RawArtifact: 10,917;
- PostingLocationResolution: 556;
- GeocoderCacheEntry: 3;
- GeocodingReviewItem: 80.

Real geospatial retry: not run. Source HTTP: 0. Geocoder HTTP: 0. Historical source files: no
mutation. Real operational root designation occurs only after independent audit and C4 merge.

## Focused validation

- C4 tests: 15 passed;
- C2/C3 storage/geospatial regressions: 73 passed;
- complete pytest suite: 531 passed locally in 144.77 seconds and in exact-head CI in
  488.11 seconds;
- Playwright browser acceptance: 4 passed in 18.06 seconds;
- Ruff: passed;
- mypy: passed across 166 local source files and 167 exact-head CI source files;
- Django check: passed;
- migration drift: none;
- backup mirror checks: passed;
- PostgreSQL restore: passed;
- RAW restore replay: passed;
- exact consolidation replay: passed.
