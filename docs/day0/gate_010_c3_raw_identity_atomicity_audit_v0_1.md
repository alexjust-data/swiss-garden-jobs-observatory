# GATE-010-C3 RAW identity and batch atomicity audit v0.1

## Scope and provenance

- baseline: merged GATE-010-C2
  `8743d1d3c4a25fb9f22f79576f960851c661769c`;
- frozen C3 contract commit:
  `0279178cf2e2bf82ba6006d52ba652d1c0b3ad18`;
- scientific resolver remains `geospatial-v0.1`;
- provider contract remains `geo-admin-searchserver-api-2026-08`;
- migrations: none;
- Source collector HTTP: zero;
- human geospatial adjudication: none.

The post-merge production attempt exposed a RAW-store lineage collision after twelve per-target
rows had committed. The exact incident is preserved in
`docs/incidents/geospatial_raw_store_lineage_collision_20260814_v0_1.md`.

## Implemented enforcement

The local RAW store now writes complete bytes to a same-directory temporary file, flushes and
fsyncs them, and publishes the final key through an atomic no-overwrite link. An already-present
object is reused only after complete byte equality; different bytes fail without modifying the
existing file. Temporary files are removed on every handled outcome.

Geocoder reconciliation independently validates:

- deterministic request and object-key identity;
- complete response SHA-256 and byte size;
- content type;
- local `RawArtifact` identity;
- cache provider/version/request/status/URLs;
- parsed response payload and immutable RAW bytes.

An existing file does not import another database's authority. The current database creates or
reuses its own exact metadata only after current response validation.

The production default RAW root is permitted only for the configured operational database.
Non-operational mutable execution must use an explicit isolated root and fails before provider
activity or evidence mutation otherwise.

Every non-dry-run Premium geospatial batch executes its complete preflight first and then resolves
all targets inside one outer database transaction. Any provider, RAW, metadata, identity or
persistence error rolls back all database evidence newly created by that invocation. Atomic
content-addressed files written before a later rollback may remain as non-authoritative orphan
bytes and are safe only through the same exact reuse checks.

## Adversarial validation

Focused tests prove:

- exact same bytes reuse the same final key without changing it;
- different bytes preserve the original and fail closed;
- 24 concurrent identical publications converge on one complete object;
- concurrent different publications produce one complete winner and one conflict;
- an exact orphan file can be independently registered in the current database;
- a conflicting orphan file creates no RAW/cache/resolution/review database evidence;
- an existing cache is revalidated against its immutable RAW bytes;
- non-operational execution against the production default root fails before mutation;
- a second-target provider failure rolls back all database rows in either target order;
- a second-target RAW conflict rolls back all database rows in either target order.

Focused implementation validation records 31 passing storage/geospatial tests, including the
exact long content-addressed incident-key shape. Ruff and mypy pass, Django check reports no
issues, and migration drift is zero.

## Operational acceptance

Acceptance used a coherent postincident backup and restore:

- backup: `.gate010c2-postmerge-artifacts/gate010c3_postincident.dump`;
- backup SHA-256:
  `6bf775041c5e08bff5f925d45cccca61b963ccd042724aa7c5551e838b1c0f22`;
- byte size: 140,484,741;
- isolated database: `swiss_garden_jobs_gate010c3_acceptance`;
- explicit isolated root: `.gate010c3-acceptance-raw`;
- restored counts: 556 resolutions, 3 caches, 80 review items and 10,917 RAW metadata rows.

Only the three locally referenced historical cache objects and the exact collision orphan were
copied into the isolated root, with complete SHA verification. Dry-run selected 51 exact Premium
targets, found the twelve incident resolutions present and identical, and found zero conflicts
without provider activity or writes.

The first implementation acceptance exposed two Windows filesystem portability defects while the
database correctly rolled back both attempts: a full content-addressed temporary filename exceeded
the effective path limit, then the workspace volume rejected hard-link publication with
`WinError 1`. The final implementation uses a bounded `.raw-*.tmp` same-directory name and
Windows atomic no-overwrite `os.rename`; POSIX retains atomic hard-link publication. The
concurrency and exact/conflicting publication tests exercise the selected platform path.

The full regression suite then exposed two pre-existing collector object keys containing a colon,
which Windows treats as Alternate Data Stream syntax and cannot receive through atomic rename.
The final physical mapping preserves the logical object key but gives Windows-invalid path
components a reserved, percent-escaped ~raw~ name. Literal percent-containing valid names remain
distinct, reserved device names and trailing dot/space are bounded, and legacy physical objects
remain readable. The LU and GL collector regressions now pass without partial publication.

The successful isolated recovery:

- reused all 12 incident resolution IDs;
- created 39 remaining resolutions in one batch transaction;
- reused four cache requests during execution;
- made nine provider requests;
- created nine local cache rows and nine local RAW metadata rows;
- produced 1 `RESOLVED`, 21 `REVIEW` and 29 `UNRESOLVED`;
- produced one mappable and 50 unmapped public records.

Poststate is 595 resolutions, 12 caches, 100 review items and 10,926 RAW metadata rows. The exact
second geospatial execution found all 51 identities, created zero evidence and made zero provider
requests.

## Corrected causal PIT

All new isolated geospatial evidence was available before cutoff
`2026-08-14T17:33:00Z`.

| Artifact | ID | Fingerprint |
|---|---|---|
| DedupRun | `f9c92adf-3547-48d8-8b95-b569f40b9d42` | `a76866a9e9710542ba8963fd91b7ee7262067c7d9d9f096b18b5d4f06e98ce4c` |
| PremiumSegmentRun | `76ece3d2-46c6-41a2-ba9e-da0467c37de4` | `49e2f453bbd652b85c62f71c1eb2a99260c1d328c60225d1657e7861ab006df9` |
| DashboardSnapshot | `a33ce5aa-45bb-4c0e-8bf3-82bef07dd92d` | `09cebf225a098abdd705795aaa5ae422fe38dad06ab4c5554522f38b751ded85` |
| Day0ReadinessAssessment | `c75f0e1d-f9df-4b89-89f7-0eea7b7dc3c7` | `603583ec4074e20f288a41877b3539880a9bd4dc526488ca90e6ea6319738b55` |

Exact replay returned every same ID and fingerprint with governed reuse. Dashboard remains one
mappable and 50 unmapped. Day-0 remains `DAY_0_BLOCKED_BY_DATA_QUALITY`: 19/29 eligible Sources,
51 active green vacancies, three critical green reviews, 21 critical geospatial reviews, zero
critical dedup reviews and a null headline.

The real operational database remains at the preserved incident boundary: 556 resolutions, three
caches, 80 review items and 10,917 RAW metadata rows. It received no acceptance or downstream
writes. Source collector HTTP remained zero.

## Final validation

- pre-independent-audit full pytest: 495 passed in 268.93 seconds;
- final corrected full pytest: 511 passed in 106.49 seconds;
- focused storage/C2/C3/legacy geospatial: 47 passed;
- browser: four passed;
- original LU and GL collector regression module: eight passed;
- concurrent identical Windows publication stress: 20/20 repeated passes;
- Ruff: passed;
- exact GitHub CI mypy inventory: passed for 162 source files;
- local correction mypy inventory: passed for 161 source files;
- Django system check: passed;
- migration drift: none;
- PostgreSQL existing-copy migration check: passed;
- PostgreSQL clean migration: passed;
- reference import on existing and clean databases, twice each: passed with identical counts;
- isolated geospatial exact retry: 51 existing, zero created, zero provider requests;
- corrected downstream exact replay: all four IDs and fingerprints reused.
## Independent-audit correction after 10f4732d

Independent audit accepted the C3 architecture and historical 12+39 recovery, then identified
three enforcement gaps at head 10f4732d4b9a3b6d48d36f46e4f894d5089e6ab2:

1. the first Windows physical mapping could alias logical components under case-insensitive
   filename semantics;
2. RAW-root isolation compared only with the repository default and could be bypassed by a custom
   production root or an injected resolver;
3. cache acceptance did not prove the exact deterministic requested URL or restrict mutually
   consistent cache/RAW content types to the SearchServer contract.

The correction leaves RawArtifact.object_key unchanged. Canonical lower-case ASCII components
remain compact; every component requiring representation receives a reserved ~raw~ prefix and
delimited lower-case UTF-8 hex escapes. The resulting physical alphabet is stable under Windows
case folding and covers upper/lower case pairs, DOS device names, forbidden characters, literal
percent, the reserved prefix, trailing dot/space and Unicode case pairs. Backslash is rejected as
a second logical separator. Pre-correction Windows paths remain read-compatible and are never
silently overwritten or migrated.

JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH now designates the actual operational root
independently from the mutable execution root. Every batch validates the effective
RawObjectStore.base_path, including injected resolvers. A non-operational database using the
designated operational root fails before provider activity or evidence mutation; an explicitly
distinct isolated root is accepted. Mutable arbitrary resolvers without a verifiable store fail
closed.

Cache reuse now recomputes request fingerprint, normalized request and exact build_url(request),
validates the same-origin final URL, HTTP 200, an accepted application/json or
application/geo+json content type, deterministic object key, full bytes, SHA-256, size and parsed
payload. The same acceptance checks are independently applied to newly fetched responses before
RAW publication or metadata creation.

Adversarial tests cover Foo/foo, CON/con, A:B/a:b, percent versus forbidden-character encoding,
reserved names, trailing dot/space, the reserved prefix and a Unicode case pair. They also cover
custom/default operational roots, injected same/distinct stores, forged same-origin requested
URLs, parseable text/plain responses, and metadata-conflict rollback in both target orders.
Twenty repeated 24-way Windows publication runs converged without partial objects or
temporary-file leakage.

The preserved isolated acceptance copy was replayed after the correction. Geospatial execution
found all 51 identities, created zero resolutions/cache/RAW/review evidence and made zero provider
requests. Dedup, Premium, Dashboard and Readiness at 2026-08-14T17:33:00Z reused the exact IDs
and fingerprints recorded above. The real operational database and the twelve incident rows
remain unchanged.
