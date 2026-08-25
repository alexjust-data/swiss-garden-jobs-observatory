# ADR 0028 — GATE-014 production scheduling and routine PIT operations

- Status: Accepted for implementation
- Upstream merged baseline: `99e39312535f33554a973110cba196c253628945`
- Stacked GATE-013 baseline: `30aed57e9e547b2cc18c65c24d01b624ccd1ea5b`
- Contract-only commit: `7be211a50efbbd835bcc1818c01f07b7d65dd7ca`
- Contract: `docs/operations/gate_014_production_scheduling_contract_v0_1.md`

## Context

GATE-012 proved the governed observatory cycle and GATE-013 integrates geospatial resolution into
`daily-observatory-cycle-v0.2`. Neither gate installs a routine external schedule. Manual invocation
does not prove exact deployment SHA, bounded runtime, no-overlap behavior, secret-free evidence or
independent verified backups.

## Decision

Keep scheduling outside Django. A portable Python wrapper validates the audited checkout, required
environment-variable names, absolute executable/log paths and bounded timeouts, then invokes one
`run_daily_observatory --trigger SCHEDULED --json` process. It propagates the cycle exit code and
captures read-only status separately.

Publish one bounded no-overwrite JSON envelope per invocation. Stable evidence binds exact argv,
Git HEAD, exit/timeout state, output hashes and bounded cycle/status identifiers. Volatile timestamps,
duration and invocation UUID stay outside its deterministic fingerprint. Secret values and private
job evidence are never persisted.

Windows Task Scheduler is the primary deployment adapter. Its deterministic plan uses one daily
calendar trigger, `IgnoreNew`, no missed-start catch-up, least privilege and a bounded execution
limit. The registration service independently revalidates environment, SHA, clean worktree and a
Windows civil timezone equivalent to Europe/Zurich. It reuses exact task XML, rejects conflicts and
never force-overwrites.

Add an independent backup wrapper using PostgreSQL custom format. It validates the clean deployment,
runs `pg_dump`, checks the result with `pg_restore --list`, hashes it and atomically publishes a
manifest. It restores nothing and deletes no retained evidence.

## Causality and failure

The scheduler creates no retry, recovery or missed-day cycle. PostgreSQL advisory locking remains the
final concurrency authority. Process timeout (124) and launch failure (125) are external technical
evidence; existing domain exit codes retain their meanings. A status-capture failure cannot turn a
failed cycle into success or prevent its envelope from being published.

A manifest-publication failure removes the dump created by that same invocation. A dump or manifest
collision fails closed. A process crash between filesystem operations can leave only unsealed orphan
bytes, never an accepted manifest.

Windows publication uses same-directory `os.rename`, which raises `FileExistsError` rather than
replacing an existing destination on Windows. POSIX publication retains hardlink-plus-unlink. This
avoids assuming NTFS hardlink support on the actual external volume while preserving atomic
no-overwrite behavior.

## Boundaries

The branch later incorporated GATE-013 exact head `91adab1839ba361de53608ee897b3bfa9df7be9a`
to preserve that cycle's explicit v0.1 geospatial identity. This changes no scheduling semantics.

GATE-014 changes no Source, lifecycle, review, Dedup, Premium, geography, Dashboard, freshness or
Day-0 semantics. It creates no migrations. The first real task registration, operational backup and
scheduler-triggered production cycle remain post-merge STOP boundaries requiring explicit
authorization.

## Consequences

- The reviewed commit, rather than whatever code happens to be current, is scheduled.
- Routine executions retain bounded, secret-free mechanical evidence.
- A missed day remains an honest gap.
- Backup creation is independently verifiable and has no implicit restore/retention behavior.
- GATE-014 can be audited without Source HTTP, geocoder HTTP or production writes.
