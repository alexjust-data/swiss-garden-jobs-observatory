# Geospatial RAW store lineage collision — 2026-08-14

## Status

Contained. GATE-010-C3 corrects storage identity, database/RAW-root isolation and batch
atomicity. The operational retry remains prohibited until C3 is independently audited and merged.

## Detection

After squash-merging GATE-010-C2 as
`8743d1d3c4a25fb9f22f79576f960851c661769c`, the production-intended
`resolve_premium_locations` execution selected the accepted 51-observation Premium cohort.
Twelve target resolutions committed before the execution reached a geocoder response whose
content-addressed file already existed in the shared default RAW root.

The operational database had no local `RawArtifact` or `GeocoderCacheEntry` for that file. The
file had been written by the isolated C2 acceptance database. The former strict write-once storage
operation rejected the second exact publication without distinguishing identical bytes from
conflicting bytes.

## Bounded incident evidence

- operational database: `swiss_garden_jobs`;
- pre-execution backup:
  `.gate010c2-postmerge-artifacts/gate010c2_pre_real_20260814T154540Z.dump`;
- backup SHA-256:
  `a5f4d4c463c51db8299ef771cf047ecb4efa20aab064e8f95fae4894794d18b6`;
- verified archive entries: 555;
- restored prestate: 544 location resolutions, 3 geocoder cache rows, 79 geocoding review
  rows and 10,917 RAW metadata rows;
- incident additions: 12 location resolutions, comprising 11 `UNRESOLVED` and 1 `REVIEW`;
- incident review additions: 1;
- incident cache additions: 0;
- incident RAW metadata additions: 0;
- downstream PIT artifacts built by the failed invocation: 0;
- Source collector HTTP: 0.

The collision request fingerprint is
`b0c9b6ea8808f4eee7835d146ec982145ede6e3db524e8207e20b7880094c491`.
The complete existing response has SHA-256
`170fb4196ca4a485a7dfd87394a564060e1e991fb9b91ed2ac4426c1e03864b4` and byte size
5,471. Its exact isolated acceptance metadata was `RawArtifact` 10918 and cache
`0fba48d7-1009-4011-a49b-b4e23bf443b7`.

## Preservation

The twelve operational rows are immutable incident evidence. They were not deleted, retargeted,
updated or replaced, and the real operational database was not restored over them. The colliding
file was not altered. No downstream reconstruction was attempted after the failure.

## Root cause

Two independent database lineages shared one mutable filesystem namespace, while storage
publication treated every pre-existing final key as an error. Per-target database transactions
also allowed earlier targets to commit before a later target failed.

The defect is operational. It does not change `geospatial-v0.1`, privacy, candidate selection,
Premium, Dashboard, Day-0 or Source semantics.

## Corrective boundary

GATE-010-C3 freezes and implements:

- atomic no-overwrite RAW publication with exact-byte idempotence;
- conflict on any different bytes under the same final key;
- independent local validation of RAW/cache metadata;
- explicit isolated RAW roots for non-operational databases;
- one outer transaction for every live Premium geospatial target batch;
- preservation and later exact reuse of the twelve incident rows.

No further real-database geospatial execution is authorized before C3 merge.
