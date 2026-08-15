# GATE-010-C3 — RAW object identity and geospatial batch atomicity contract v0.1

Status: FROZEN BEFORE C3 IMPLEMENTATION OR ACCEPTANCE

Baseline: merged GATE-010-C2 `8743d1d3c4a25fb9f22f79576f960851c661769c`.

## Purpose

The first post-merge C2 execution exposed an operational identity defect. An isolated acceptance
database and the operational database used the same local RAW root. The isolated database had
persisted a valid swisstopo response file and its own database metadata. The operational database
had no corresponding RawArtifact or GeocoderCacheEntry. Re-fetching the same bytes produced the
same governed object key, and the write-once store rejected the already-present file.

Before that failure, twelve valid per-target location resolutions had committed in the operational
database. They are immutable incident evidence and are not deleted, retargeted or rewritten.

C3 governs storage and failure enforcement only. It does not change geospatial-v0.1 resolution,
privacy, candidate matching, thresholds, Premium, Dashboard, Day-0, Source or lifecycle semantics.

## Incident boundary

The pre-C2 operational backup is:

- artifact: `.gate010c2-postmerge-artifacts/gate010c2_pre_real_20260814T154540Z.dump`;
- SHA-256: `a5f4d4c463c51db8299ef771cf047ecb4efa20aab064e8f95fae4894794d18b6`;
- archive entries: 555.

The verified restored prestate contains 544 PostingLocationResolution rows, three geocoder cache
rows, 79 geocoding review rows and 10,917 RawArtifact rows.

The failed operational attempt added exactly twelve PostingLocationResolution rows: eleven
UNRESOLVED and one REVIEW. It added one GeocodingReviewItem and no GeocoderCacheEntry or
RawArtifact. No downstream PIT artifact was built. Source collector HTTP was zero.

The collision identity is:

- request fingerprint:
  `b0c9b6ea8808f4eee7835d146ec982145ede6e3db524e8207e20b7880094c491`;
- response SHA-256:
  `170fb4196ca4a485a7dfd87394a564060e1e991fb9b91ed2ac4426c1e03864b4`.

## RAW object identity

A RAW object is identified by its validated relative object key and complete immutable bytes.
SHA-256 and byte size are independently recomputed from those bytes.

Publishing a previously absent object uses an atomic no-overwrite filesystem operation. A reader
must never observe a partially written object at its final key.

If the final object key already exists:

- exact byte equality, exact SHA-256 and exact size mean PRESENT_IDENTICAL and may be reused;
- any byte, SHA-256 or size difference means PRESENT_CONFLICTING and fails closed;
- existing bytes are never overwritten, truncated, appended, deleted or renamed.

Exact reuse is storage idempotence, not imported scientific authority. A database may create or
reuse its own RawArtifact and cache metadata only from evidence independently validated in that
database execution. Database rows are never copied merely because a file exists.

## RawArtifact and cache reconciliation

After a current provider response is independently validated:

1. derive its deterministic object key;
2. atomically publish or exactly reuse the immutable bytes;
3. create or reuse the local RawArtifact only when object key, SHA-256, byte size and content type
   are identical;
4. create or reuse the local GeocoderCacheEntry only when request identity, response metadata,
   RawArtifact and parsed payload are identical.

Any local metadata conflict fails closed. An isolated database row is not authority for the
operational database.

## Database-to-RAW-root scope

Operational and isolated mutable executions must not accidentally share the default production RAW
root.

The operational database `swiss_garden_jobs` may use the configured production root. Any other
database executing the governed C2/C3 batch must use an explicitly configured, distinct
`JOB_OBSERVATORY_RAW_STORE_PATH`. A non-operational database using the production default fails
before provider activity or evidence mutation.

Tests that inject a temporary RawObjectStore remain isolated by construction.

This rule does not prohibit read-only inspection of historical files. It governs mutable batch
execution.

## Batch transaction and failure

The complete deterministic Premium target and existing-resolution fingerprint preflight from C2
remain mandatory.

For a live batch, all database mutations for new target resolutions, review items, cache rows and
RawArtifact rows occur inside one outer database transaction. Per-target transactions may be
nested savepoints but may not commit independently.

If any target raises because of HTTP, response validation, RAW identity, local metadata,
resolution identity or persistence:

- the batch raises and creates no new database evidence from that invocation;
- pre-existing identical evidence remains unchanged;
- no downstream PIT is built;
- provider/source failure does not create lifecycle-negative evidence.

Validated content-addressed bytes may have been atomically published before a later database
rollback. Such unreferenced bytes are not accepted scientific evidence. A retry may reuse them only
through the exact-byte rules above and must independently create/validate local metadata.

No cleanup procedure may delete an immutable final-key object merely because a database
transaction rolled back.

## Retry and the twelve incident rows

The twelve operational incident resolutions are pre-existing immutable evidence. C3 does not
manufacture a rollback or mutate them.

After C3 is independently audited and merged, the exact operational retry:

- reuses those twelve rows after fingerprint equality;
- resolves only the remaining targets;
- safely handles the pre-existing identical response file;
- creates no duplicate resolution, cache, RAW metadata or review evidence;
- builds a new causal PIT only after the complete target succeeds.

Exact second retry must perform zero provider requests and reuse every resulting ID.

## Isolation acceptance

Before publication, acceptance uses a copy of the post-incident operational database and an
explicit isolated RAW root. The real operational database receives no further C3 writes.

Acceptance must prove:

- exact existing file + exact bytes is reused without overwrite;
- existing file + different bytes fails closed and preserves the original;
- concurrent identical publication converges to one complete file;
- non-operational DB + production default RAW root fails before provider/writes;
- two-target batch + provider/RAW failure on either ordering creates zero new DB evidence;
- successful recovery reuses the twelve incident rows and completes the remaining target;
- exact retry creates nothing and performs zero provider requests;
- downstream PIT replay is deterministic on the isolated copy.

## STOP conditions

C3 stops without real-database continuation if:

- exact object identity cannot be verified;
- a conflicting file or local metadata row exists;
- the twelve incident resolutions conflict with current governed input;
- isolation cannot be enforced before mutable acceptance;
- atomic database rollback cannot prevent new partial target evidence;
- geospatial, privacy or another frozen scientific contract would need semantic change.

## Integrity

C3 introduces:

- no Source HTTP;
- no Source recovery;
- no human geospatial adjudication;
- no change to protected/public request construction;
- no change to marker eligibility;
- no change to Dedup, Premium, Dashboard or Day-0 policy;
- no mutation of historical snapshots or the twelve incident resolutions.

The governing invariant is:

same final RAW key + same complete bytes
→ reusable immutable storage object

same final RAW key + different bytes
→ conflict

and:

one governed geospatial batch invocation
→ all new database evidence commits
or none of it commits.
