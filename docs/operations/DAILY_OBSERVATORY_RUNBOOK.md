# Daily Observatory Runbook

## Run and inspect

Prepare PostgreSQL, migrate, and import reference data. Run exactly one scheduler invocation:

```bash
python manage.py run_daily_observatory --trigger MANUAL --json
python manage.py observatory_status --json
```

Exit zero means the operational chain completed. `SUCCEEDED_NOT_AUTHORIZED` is a valid scientific
result, not a scraper failure. Read `quality_state.authorization_blockers` to see why no headline is
published. Non-zero exit codes are documented in the frozen operating contract.

The status payload identifies the latest cycle, last successful cycle, age, exact PIT cutoff,
Source failures, critical reviews, authorization state, and pinned artifact IDs/fingerprints.

## Diagnose a failure

Inspect the cycle's `stage_statuses`, `failure.code`, and append-only `OperationalEvent` rows. Each
`ObservatorySourceAttempt` pins the Source, CollectionRun, health, completeness, counters, and
runtime. Never interpret a failed Source as zero jobs or manually close its Postings.

Pending green reviews are `GreenRelevanceAssessment(result=REVIEW)` without effective resolved
authority. Pending dedup reviews are `DedupReviewItem(review_status=PENDING)`. The cycle never makes
human decisions.

Blocked Sources are the nine entries in `day0.policy.FINAL_BLOCKED_REQUIRED_SOURCES`; the daily
command refuses them before adapter or HTTP creation. Recovery requires a separate scientific gate.

## Safe retry and recovery

Keep the emitted cycle UUID. A successful exact retry is network-free:

```bash
python manage.py run_daily_observatory --cycle-id <UUID> --trigger MANUAL --json
```

An interrupted or failed same-cycle continuation requires explicit recovery:

```bash
python manage.py run_daily_observatory \
  --cycle-id <UUID> --trigger RECOVERY --resume --timeout-seconds 14400 --json
```

Do not retry blindly while another invocation may be active. The PostgreSQL advisory lock refuses a
second process before HTTP. Do not change cohort/configuration under an existing cycle ID. Do not
retry to erase a scientific `NOT_AUTHORIZED` result.

## Freshness, history, and replay

Freshness remains the frozen inclusive 72-hour policy over accepted healthy complete FULL_SOURCE
runs. The status command reports the latest persisted state. Every successful daily cycle retains
its exact collection and downstream references; missed dates are gaps, never synthetic cycles.

To verify replay, rerun the successful cycle ID and compare IDs/fingerprints. The result must report
`exact_cycle_retry_reused=true` and perform no HTTP.

## Backup and restore

Backups are external to the cycle. Never put credentials in a command, repository, logs, or cycle
evidence. With environment-based PostgreSQL credentials:

```bash
pg_dump --format=custom --file=<controlled-target>/observatory.dump "$POSTGRES_DB"
pg_restore --list <controlled-target>/observatory.dump
```

Restore only into an isolated database. Apply `pg_restore`, run `python manage.py check`, run the
reference import twice, then read the latest `ObservatoryCycle` and its four pinned artifacts. Never
restore over the operational database during a smoke test.

Escalate to a new scientific gate if operation exposes a meaning/identity/classification/policy
defect. Scheduler, timeout, deployment, or backup infrastructure changes that preserve meaning stay
operational.
