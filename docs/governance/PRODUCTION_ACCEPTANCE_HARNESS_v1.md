# H2 — Production Acceptance Harness v0.1

## Purpose

`scripts/production_acceptance.py` collects mechanically verifiable evidence around one
bounded operational execution. H2 is not a scientific contract, a policy authority, or
an approval mechanism.

H2 may report `PASS`, `FAIL`, or `NOT_PROVEN`. A `PASS` means that every mandatory
mechanical invariant configured by the bounded adapter was proved. It never means that
the operation or a pull request is independently approved.

## Version 1 operation

Version 1 exposes one allowlisted operation:

```text
geospatial-recovery
```

No profile or command-line argument can supply a shell command, Python callable,
resolver override, alternate provider, or alternate evidence validator.

The production CLI requires:

- the exact `PremiumSegmentRun` UUID;
- the exact connected database name;
- `--execute` for mutation;
- `--verify-raw-bytes` for mutation;
- `--allow-operational` when the connected database is the configured operational DB.

`--allow-operational` is an acknowledgement of an authorization already granted
outside H2. It does not grant authority itself. The first real operational use remains
behind independent audit and explicit user authorization.

## Evidence sequence

```text
read-only REPEATABLE READ snapshot BEFORE
        ↓
RAW byte verification
        ↓
bounded geospatial batch
        ↓
read-only REPEATABLE READ snapshot AFTER
        ↓
exact batch retry
        ↓
read-only REPEATABLE READ snapshot RETRY
        ↓
delta checks + canonical report
```

Every database snapshot binds:

- sanitized PostgreSQL server identity;
- database name;
- PostgreSQL transaction snapshot identifier;
- transaction timestamp;
- applied migration inventory hash;
- counts and per-row hashes for governed models;
- bounded PIT artifact IDs and input fingerprints;
- logical RawArtifact inventory;
- optional complete physical RAW byte inventory.

Reports contain hashes and governed IDs, not database credentials, DSNs, request URLs,
job descriptions, private addresses, or geocoder query material.

## Governed model inventory

H2 v0.1 snapshots:

- `RawArtifact`;
- `GeocoderCacheEntry`;
- `PostingLocationResolution`;
- `GeocodingReviewItem`;
- `DedupRun`;
- `PremiumSegmentRun`;
- `DashboardSnapshot`;
- `Day0ReadinessAssessment`;
- `ObservatoryCycle`;
- `ObservatorySourceAttempt`.

Existing row deletion or mutation fails. For `geospatial-recovery`, only new RAW,
geocoder-cache, location-resolution and geocoding-review rows are allowed. Exact retry
allows no new, modified, or deleted governed row.

## HTTP evidence

The geospatial adapter invokes no Source collection entrypoint. H2 instruments both the
fixed `GeoAdminSearchServerClient.fetch` boundary and the project's governed urllib
transport boundary. It records counts only, never URLs or queries. Provider fetches are
reconciled with the governed batch result, Source transports must be zero, and exact
retry requires zero provider fetches.

H2 never converts absent instrumentation into zero. Future operation adapters must add
bounded instrumentation or return `NOT_PROVEN`; a mandatory `NOT_PROVEN` prevents an
overall PASS.

## RAW boundary

Mutable acceptance requires every `RawArtifact` to resolve to physical bytes with the
same SHA-256 and size. An isolated DB must use an absolute RAW root distinct from the
operational root. An operational DB must use the designated operational root and valid
C4 sentinel. Report output and RAW storage must be physically disjoint.

A RAW preflight failure stops before geospatial execution.

## Canonical output

Default reports are written to the git-ignored `.production-acceptance/` directory.
JSON values use deterministic sorting and normalized UTC timestamps. Runtime duration
is separated under `volatile`; the evidence SHA-256 binds the substantive report.
Publication uses a same-directory temporary file, flush/fsync, and atomic replacement.

## Dry-run

Omitting `--execute` runs the geospatial batch preflight only. Mutation, provider
requests, and exact retry are not accepted as proven. The correct overall result is
`NOT_PROVEN`, not PASS.

Example isolated preflight:

```powershell
python scripts/production_acceptance.py --operation geospatial-recovery --premium-run <UUID> --expected-database <ISOLATED_DB> --output-dir .production-acceptance/preflight
```

The first real production execution additionally requires the externally audited and
authorized command flags:

```powershell
python scripts/production_acceptance.py --operation geospatial-recovery --premium-run <UUID> --expected-database swiss_garden_jobs --execute --allow-operational --verify-raw-bytes --output-dir <EXTERNAL_REPORT_DIR>
```

Do not run the production form until the explicit production-mutation checkpoint is
approved.
