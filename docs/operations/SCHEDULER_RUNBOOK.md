# External Scheduler Runbook

GATE-014 keeps scheduling outside Django. The deployed action executes exactly one governed cycle,
then captures read-only status. It does not retry, resume, recover or fabricate a missed day.

## Deployment prerequisites

Use an audited, clean checkout at an exact 40-character commit SHA. Configure these environment
variable names in the deployment account without putting their values in task arguments:

```text
DJANGO_SECRET_KEY
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD (when the PostgreSQL deployment requires it)
POSTGRES_HOST
POSTGRES_PORT
JOB_OBSERVATORY_RAW_STORE_PATH
JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH
JOB_OBSERVATORY_RAW_LINEAGE_MANIFEST_SHA256
```

The log and backup roots must be absolute and outside every Git worktree. Windows must use a civil
time zone equivalent to Europe/Zurich (`W. Europe Standard Time` or `Romance Standard Time`). The
Task Scheduler trigger uses local wall-clock time; Microsoft documents `StartBoundary` as the time
at which a calendar trigger activates.

## Read-only scheduler plan

Run the wrapper dry plan first. It validates paths, environment names, exact SHA and cleanliness
while performing no Django execution, database/RAW write, Source HTTP or provider HTTP:

```powershell
python scripts/run_scheduled_observatory.py --repo-root <AUDITED_CHECKOUT> --python <PYTHON_EXE> --log-root <EXTERNAL_LOG_ROOT> --expected-head <AUDITED_SHA> --dry-run
```

Generate the deterministic Windows task plan without registering anything:

```powershell
python scripts/configure_windows_scheduler.py --start-boundary 2026-09-01T03:17:00 --repo-root <AUDITED_CHECKOUT> --python <PYTHON_EXE> --log-root <EXTERNAL_LOG_ROOT> --expected-head <AUDITED_SHA> --show-xml
```

The governed XML sets:

```text
daily interval                 1
multiple instances            IgnoreNew
missed-start catch-up          false
run level                     LeastPrivilege
network required              true
execution limit               bounded
credentials in arguments      false
```

Actual `--apply` is a production mutation. It is permitted only after independent audit and explicit
activation authorization. The service revalidates environment, exact SHA, clean worktree and host
timezone before it queries or creates the task. An identical task is reused; a conflicting task under
the governed name fails closed; `/F` overwrite is never used.

## Invocation evidence and exit behavior

The task runs `scripts/run_scheduled_observatory.py`, which invokes:

```text
python manage.py run_daily_observatory
  --trigger SCHEDULED
  --timeout-seconds <bounded>
  --json
```

The wrapper returns the cycle's exact exit code. Exit zero includes `SUCCEEDED_NOT_AUTHORIZED` and is
not evidence of Day-0 authorization. Process timeout is 124 and process-launch failure is 125. A
status-capture failure is recorded separately and never changes the cycle exit code.

One secret-free, no-overwrite JSON envelope is published in the external log root. It contains
timestamps, SHA/exit evidence and bounded cycle/status identifiers—not raw descriptions, contacts,
DSNs, passwords or environment values.

## Backup plan and execution

Backups are independent from the daily cycle. Plan one without writes:

```powershell
python scripts/backup_observatory.py --repo-root <AUDITED_CHECKOUT> --output-root <EXTERNAL_BACKUP_ROOT> --expected-head <AUDITED_SHA> --pg-dump <PG_DUMP_EXE> --pg-restore <PG_RESTORE_EXE> --dry-run
```

Removing `--dry-run` is a production write and requires the separately authorized backup procedure.
It creates a PostgreSQL custom-format dump, validates it with `pg_restore --list`, computes SHA-256
and publishes a no-overwrite manifest. It never restores or deletes retained backups.

## Recovery and alert boundary

A killed process may leave a `RUNNING` cycle. Inspect persisted status and use the explicit recovery
command in `DAILY_OBSERVATORY_RUNBOOK.md`; never create a synthetic replacement day. The database
advisory lock remains the final concurrency authority.

Alert consumers use exit codes, deterministic status and append-only operational events. Do not page
daily for the unchanged structural 20/29 deficit. Alert on a new cycle failure, incomplete/degraded
Source, freshness expiry, continuity conflict, geospatial or Dashboard failure, cohort drift, or an
authorization transition.

Microsoft references:

- https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-startboundary-triggerbasetype-element
- https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks-create
