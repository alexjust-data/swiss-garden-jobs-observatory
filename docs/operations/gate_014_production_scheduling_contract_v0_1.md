# GATE-014 — Production scheduling and routine PIT operations contract v0.1

Status: `FROZEN_BEFORE_IMPLEMENTATION`

- Stacked baseline: GATE-013 exact head
  `30aed57e9e547b2cc18c65c24d01b624ccd1ea5b`.
- Upstream merged main: GATE-010-C4
  `99e39312535f33554a973110cba196c253628945`.
- Operational cycle contract: `daily-observatory-cycle-v0.2`.

## 1. Purpose

GATE-014 turns the already-governed daily Observatory Cycle into a deployable,
externally scheduled routine. It adds no scheduler daemon to Django and no new
scientific interpretation. The deployment scheduler invokes one bounded
process, retains its evidence, and exposes failure through the existing exit
codes and persisted operational status.

The primary deployment target is Windows Task Scheduler. The cycle runner is a
portable Python entry point so another external scheduler can use the same
contract later.

## 2. Frozen scientific boundary

GATE-014 changes none of the following:

- the 29-Source required universe or 24/29 Day-0 minimum;
- Source access, collection, lifecycle, review, dedup, Premium, geography,
  privacy, Dashboard, freshness or authorization semantics;
- `daily-observatory-cycle-v0.2` stage order or cutoff behavior;
- historical cycles, attempts, events, PIT artifacts, RAW evidence or review
  authority;
- `docs/research/v0_4/`.

The scheduler never turns `SUCCEEDED_NOT_AUTHORIZED` into a technical failure.
Exit zero retains its existing meaning.

## 3. One external invocation

The scheduled cycle action is exactly one process rooted at the checked-out
repository and equivalent to:

```text
python manage.py run_daily_observatory
  --trigger SCHEDULED
  --timeout-seconds <bounded>
  --json
```

The wrapper may then invoke read-only `observatory_status --json`. It may not
create a second cycle, silently retry, resume, recover, recollect, change the
cohort or alter the cutoff.

The child's governed exit code is the scheduled action's exit code. Failure of
the subsequent read-only status capture is recorded separately and cannot turn
a failed cycle into success.

## 4. Cadence and missed days

The deployment chooses one wall-clock time in `Europe/Zurich`. GATE-014 does not
hard-code that time in shared code. The task runs once per calendar day and:

- does not start a second overlapping process;
- does not queue overlapping invocations;
- does not automatically backfill a missed day;
- does not fabricate a cycle for a missed day;
- does not enable "run as soon as possible after a missed start".

The PostgreSQL advisory lock remains the final concurrency authority even when
the external scheduler is correctly configured.

## 5. Bounded runtime and recovery

The scheduled wrapper and the Django command both receive explicit bounded
timeouts. The external process timeout is longer than the governed Django
timeout and records a process-level timeout without pretending a hard kill was
a clean domain failure.

No automatic recovery is performed. A failed, interrupted or stale cycle is
diagnosed using its persisted cycle ID and resumed only through the existing
explicit `RECOVERY --resume` runbook. A successful cycle retry remains
network-free and is never part of ordinary scheduling.

## 6. Logs and machine evidence

The wrapper writes only to an explicitly configured absolute log directory
outside every Git worktree. It publishes one no-overwrite JSON envelope per
invocation using temporary-file plus atomic rename semantics. The envelope
records bounded operational metadata:

- wrapper version;
- start/end UTC timestamps and duration;
- repository root and Git HEAD, without local diffs or file payloads;
- exact child argv with no credentials;
- child exit and timeout state;
- SHA-256 of captured stdout and stderr;
- parsed bounded cycle/status identifiers when valid;
- read-only status command result;
- a deterministic invocation fingerprint over stable evidence.

Full descriptions, contact data, raw payloads, passwords, DSNs, environment
values and private evidence are forbidden. Human-readable stdout/stderr may be
retained by the external scheduler, but the governed envelope stores hashes and
bounded parsed fields only.

## 7. Secrets and execution identity

Credentials are supplied only through the deployment account's environment or
secret mechanism. They never appear in task arguments, generated task XML,
repository files, wrapper JSON, stdout or logs. The task runs as an explicitly
chosen existing OS identity and does not create users, elevate privileges or
store a password in the repository.

The Python executable, repository root and log root are absolute, validated
paths. The wrapper refuses a dirty repository and a HEAD different from the
configured deployment SHA. This prevents silently scheduled unreviewed code.

## 8. Windows task plan and activation

Repository tooling produces a deterministic, sanitized Windows Task Scheduler
plan. Without an explicit apply switch it is read-only and creates no task.
The plan binds:

- task name;
- absolute Python and repository paths;
- expected deployment SHA;
- daily local start time;
- Django and process timeouts;
- absolute external log directory;
- `IgnoreNew` multiple-instance policy;
- disabled missed-start catch-up;
- bounded execution time;
- non-zero exit visibility.

Actual task registration is a post-merge production mutation and is forbidden
before independent audit and explicit activation authorization.

## 9. Backup boundary

Backups remain independent of a cycle. GATE-014 provides a bounded backup entry
point that executes PostgreSQL custom-format `pg_dump`, validates it using
`pg_restore --list`, computes SHA-256 and atomically publishes a no-overwrite
manifest beside the dump. It consumes credentials only from the environment.

The backup tool has no retention deletion and never restores over an existing
database. Acceptance uses an isolated database and external temporary target.
Scheduling or applying a real operational backup is a post-merge production
mutation.

## 10. Monitoring and alerts

The task exposes the existing governed exit code and captures deterministic
`observatory_status`. Append-only `OperationalEvent` remains the domain alert
source. GATE-014 does not add email, SMS, paging or a telemetry platform.

The unchanged structural 20/29 deficit does not generate daily alert spam.
New cycle failure, incomplete/degraded Source, continuity conflict, geospatial
failure, Dashboard failure, freshness loss, cohort drift or authorization
transition remains visible through existing persisted evidence and non-zero
execution where applicable.

## 11. Idempotence and dry run

Dry run validates paths, HEAD, cleanliness, arguments, environment variable
presence and the intended task plan while performing:

- zero Django command execution;
- zero DB writes;
- zero RAW writes;
- zero Source HTTP;
- zero provider HTTP;
- zero scheduler registration.

Running the same task-plan generator twice produces the same substantive plan.
An already-identical registered task may be reused after activation; a
different existing task under the same governed name fails closed.

## 12. Acceptance

Before a draft PR is ready:

1. wrapper unit and adversarial tests pass;
2. exact exit-code propagation and process-timeout behavior pass;
3. log publication is atomic, no-overwrite and secret-free;
4. repository SHA/cleanliness drift fails before Django execution;
5. task plan proves no overlap and no missed-start catch-up;
6. task registration is tested only against an isolated test task name and is
   removed after the test, or is mechanically verified without registration;
7. backup entry point is proven on an isolated PostgreSQL database and restore
   inventory;
8. exact dry-run replay is deterministic;
9. full tests, Ruff, mypy, Django check and migration drift pass;
10. H1 reports `READY FOR SEMANTIC AUDIT`.

No production cycle, task registration, real backup, Source HTTP or provider
HTTP is required before merge.

## 13. STOP boundaries

Stop and report before:

- registering or modifying the real scheduled task;
- running the first scheduler-triggered operational cycle;
- writing the real operational backup target;
- modifying production DB or canonical RAW outside the already-audited cycle;
- changing any scientific contract or frozen research;
- weakening exit, timeout, recovery, privacy or access semantics;
- silently accepting a dirty/different deployment checkout;
- embedding credentials in any artifact.

