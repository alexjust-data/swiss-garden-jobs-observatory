# FULL_SOURCE freshness policy v0.1

## Decision

Policy version: `full-source-freshness-v0.1`.

For assessment cutoff `T`, the governed freshness timestamp is `CollectionRun.finished_at`, because this is when complete acquisition evidence became causally available. The selected evidence is the latest causally available `FULL_SOURCE + SUCCEEDED + HEALTHY + snapshot_complete + counter-equal` run by `T`.

```text
age = T - selected_run.finished_at
FRESH iff age <= 72 wall-clock hours
```

The boundary is inclusive. There are no hidden weekend or holiday exceptions. Seventy-two hours permits a daily observatory to cross one weekend and one bounded operational retry while preventing evidence older than three days from being presented as current.

## Run and failure semantics

- A blocked Source is `BLOCKED`, not stale, and remains `NOT_COVERED`.
- An implemented Source without accepted evidence is `NO_ACCEPTED_RUN`.
- Evidence older than 72 hours is `STALE` and does not enter current coverage, regardless of vacancy count.
- Accepted FULL_SOURCE evidence and latest current-health evidence are distinct. A later failed, degraded, or outage activity does not rewrite a prior accepted snapshot, but invalidates current health. A later governed healthy diagnostic may restore current health while that accepted healthy FULL_SOURCE remains fresh.
- Failed/incomplete attempts never create zero demand or negative lifecycle truth.
- Historical replay uses only runs finished by the historical `as_of`; future runs cannot repair the past.

The window is an observability limit, not permission to conceal collector failures. Operational monitoring should still target daily successful runs.
