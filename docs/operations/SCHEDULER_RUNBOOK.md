# External Scheduler Runbook

The scheduler executes one process; Django contains no daemon:

```text
working directory: repository root
command: python manage.py run_daily_observatory --trigger SCHEDULED --json
frequency: one governed FULL_SOURCE cycle per calendar day
concurrency: prohibited by the database lock
stdout/stderr: retained by the scheduler
success: exit 0, including SUCCEEDED_NOT_AUTHORIZED
retry: bounded; reuse the emitted cycle ID with RECOVERY --resume
```

Provide environment variables through the scheduler's secret mechanism. Never commit credentials.
Set a whole-process timeout longer than observed Source runtimes. A killed process may leave a
`RUNNING` row; inspect status and use explicit recovery rather than fabricating a replacement day.

Linux example (illustrative cron entry, deployment chooses the actual window):

```cron
17 3 * * * cd /srv/observatory && /srv/venv/bin/python manage.py run_daily_observatory --trigger SCHEDULED --json
```

For systemd, use a oneshot service plus timer with `Persistent=false`, bounded runtime, non-zero exit
alerting, and captured journal output. On Windows Task Scheduler, set the repository as "Start in",
invoke the virtualenv Python directly, prohibit overlapping instances, capture output, and treat exit
zero as operational success. Do not use a machine-specific path in shared configuration.

Alert hooks consume the JSON/status and append-only event codes. Do not page daily for the unchanged
known 20/29 structural deficit; page for new cycle failure, degraded/incomplete Source, freshness
expiry, continuity conflict, Dashboard incompatibility, cohort change, or authorization transition.
