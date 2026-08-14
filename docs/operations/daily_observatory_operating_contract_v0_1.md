# Daily Observatory Operating Contract v0.1

Status: `FROZEN_FOR_IMPLEMENTATION`  
Cycle version: `daily-observatory-cycle-v0.1`  
Gate: `GATE-012`

## 1. Scope and invariant

This contract governs how the already-frozen scientific pipeline is run repeatedly. It does not
change Posting, Vacancy, lifecycle, green relevance, human review, deduplication, Premium,
coverage, freshness, authorization, geography, privacy, or Job-Room semantics.

The invariant is:

```text
governed implemented Source cohort
-> FULL_SOURCE collection attempts
-> source health/completeness evidence
-> green review continuity
-> Dedup at one causal cutoff
-> dedup review continuity
-> aligned Dedup rebuild when continuity changes authority
-> Premium
-> Dashboard
-> Day-0 readiness
-> one immutable completed-cycle result
```

Scientific uncertainty is retained. Operational automation must never manufacture a human
decision, absence, closure, authorization, or recovered Source.

## 2. Cycle identity and configuration

An Observatory Cycle is one attempted production-intended refresh. Its caller supplies or receives
an immutable UUID `cycle_id`. Exact retry uses the same ID; a legitimate later invocation uses a new
ID. Cycle identity is not a date and missed dates never create synthetic cycles.

The configuration fingerprint is lower-case SHA-256 of canonical JSON containing:

- cycle version;
- trigger (`MANUAL`, `SCHEDULED`, or `RECOVERY`);
- target cohort version and the sorted selected Source IDs;
- the frozen Day-0 universe, coverage, freshness, and authorization versions;
- green classifier/review/material versions;
- dedup/normalizer/review-material versions;
- Premium version;
- orchestration stage order and cutoff policy identifier;
- the code Git SHA when available, otherwise the explicit bounded value `UNKNOWN`.

The cohort version is `day0-source-universe-v0.2` plus the terminal C-6 dispositions. Cohort size is
derived, never hardcoded.

## 3. Source selection

The production cohort is exactly the required Sources whose frozen terminal disposition is
`ACCEPTED_IMPLEMENTED`. A required `ACCEPTED_BLOCKED` Source is excluded before adapter creation or
HTTP activity. Any blocked Source in a requested override or resolved cohort fails closed with
`BLOCKED_SOURCE_SELECTED` before collection begins.

GATE-012 performs no blocked-source reconnaissance, recovery, probe, or production request.

## 4. Status machine

Persisted terminal statuses are:

- `SUCCEEDED`: technically valid cycle whose Day-0 assessment is authorized;
- `SUCCEEDED_NOT_AUTHORIZED`: technically valid cycle whose Day-0 assessment is not authorized;
- `FAILED_COLLECTION`;
- `FAILED_COMPLETENESS`;
- `FAILED_CONTINUITY`;
- `FAILED_DEDUP`;
- `FAILED_PREMIUM`;
- `FAILED_DASHBOARD`;
- `FAILED_READINESS`;
- `ABORTED_CONCURRENCY`.

Non-terminal states are `PLANNED` and `RUNNING`. Stage statuses are `PENDING`, `RUNNING`,
`SUCCEEDED`, `SKIPPED`, or `FAILED`. A failure always records its stage-specific code and bounded
evidence. `SUCCEEDED_NOT_AUTHORIZED` exits successfully; scientific non-authorization is not a
technical failure.

## 5. Ordering and cutoff

The mandatory order is:

1. resolve and validate the governed cohort;
2. collect each Source with the existing governed FULL_SOURCE pipeline;
3. persist exact per-Source attempt evidence;
4. apply green continuity to collected assessments;
5. choose provisional cutoff only after green applications are available;
6. run/reuse Dedup at that cutoff;
7. apply dedup continuity to every eligible review pair using only independently validated 011G
   authority;
8. if a new dedup application was created after the provisional cutoff, advance the final cutoff
   beyond it and run/reuse Dedup again so the run can causally consume it;
9. run/reuse aligned Premium at the final cutoff;
10. build/reuse Dashboard at the same final cutoff;
11. build/reuse Day-0 readiness at the same final cutoff;
12. seal the cycle with all exact IDs, fingerprints, source runs, quality state, and events.

The final cutoff is an aware UTC timestamp no earlier than every selected CollectionRun completion,
continuity application creation, and other evidence intended for the downstream chain. Dedup,
Premium, Dashboard, and readiness use exactly that cutoff. No future evidence may leak backward.

## 6. Collection semantics

Every selected Source receives one governed FULL_SOURCE attempt in a new cycle. Existing collection
code remains authoritative for GET/POST governance, immutable RAW, SHA-256, observations, green
assessments, source health, completeness, counters, and lifecycle.

Per-Source evidence pins Source ID, CollectionRun ID, attempt/finish times, run status, health,
snapshot completeness, listing/fetch/observation/assessment/lifecycle counters, and runtime. A
technical failure may have no CollectionRun ID and still records bounded failure evidence.

Failed, degraded, incomplete, blocked, 403/429, layout-changed, or outage evidence never implies a
zero-job snapshot, negative lifecycle evidence, disappearance, or closure. Existing freshness and
Day-0 rules decide whether prior accepted FULL_SOURCE evidence remains eligible.

Collection phase may continue across Sources after one Source fails so exact source-level evidence
is retained. Downstream construction is permitted only when the existing services can construct a
causal, scientifically valid PIT result; otherwise the cycle terminates at the precise failed stage.

## 7. Concurrency

At most one non-terminal production cycle may hold authority for the same cycle/cohort version.
PostgreSQL advisory locking is authoritative; the persisted running-cycle conflict is also checked
inside the transaction. The winner obtains authority before adapter construction. A loser records
or returns `ABORTED_CONCURRENCY`, performs zero Source HTTP requests, and exits non-zero.

The lock is held for the complete invocation and is connection-scoped. An abandoned database row
does not itself own the lock. A new cycle encountering a stale `RUNNING` row records a
`STALE_CYCLE_DETECTED` alert and fails closed unless explicitly invoked as governed recovery.

## 8. Retry, resume, and interruption

`--cycle-id` names exact identity. Reusing it with an unequal configuration fingerprint fails
closed. Retrying a terminal successful cycle returns its stored result without network or new
scientific artifacts. Retrying an aborted concurrency attempt may acquire authority and continue.

A retry of an interrupted/failed cycle never deletes the first attempt. Source attempts are
append-only. A Source with a pinned successful, healthy, complete CollectionRun in the same cycle is
not recollected; incomplete or failed attempts may be retried as a new attempt row only when
`--resume` is explicit. Existing exact-fingerprint services provide downstream idempotence.

A cycle is stale when `RUNNING` without a heartbeat newer than the configured operational timeout.
Stale detection records evidence; it does not mutate scientific artifacts. Recovery is explicit,
uses trigger `RECOVERY`, and preserves all earlier attempts.

## 9. Review continuity

Green continuity runs under `green-review-material-v0.1`; dedup continuity runs under
`dedup-review-material-v0.1`. Both retain the 011G identity, material equality, version, provenance,
causality, ambiguity, idempotency, and direct/inherited XOR rules. The cycle creates no HUMAN
decision. A continuity conflict is `FAILED_CONTINUITY` and fail-closed.

The cycle records created, reused, unmatched, and conflict counts separately for green and dedup.

## 10. Downstream alignment

Dedup and Premium must select the exact same observation universe. Dashboard compatibility checks
remain mandatory. The cycle pins exact IDs and fingerprints for DedupRun, PremiumSegmentRun,
DashboardSnapshot, and Day0ReadinessAssessment. A completed cycle never resolves these references
again from mutable current state.

Exact retry must return the same governed IDs and fingerprints, with one artifact per fingerprint
where the existing contract defines uniqueness.

## 11. Operational and authorization quality

Quality has separate dimensions:

- `operational_health`: `GREEN`, `AMBER`, or `RED`;
- `source_cohort_health`: exact counts and Source IDs by healthy, incomplete, degraded, outage,
  failed, and fresh status;
- `authorization_state`: the persisted Day-0 status and blockers;
- `banner`: a bounded human-readable explanation derived from those dimensions.

`GREEN` means orchestration completed and all selected attempts were successful, healthy, complete,
counter-consistent, and fresh. `AMBER` means a scientifically valid cycle completed using permitted
historical evidence while one or more current Source attempts are degraded/incomplete/failed, or
freshness is approaching its frozen limit. `RED` means the operational pipeline failed or no valid
current state was built. A structural 20/29 coverage deficit may coexist with operational `GREEN`
and authorization blocked.

## 12. Exit codes

- `0`: `SUCCEEDED` or `SUCCEEDED_NOT_AUTHORIZED`, including exact successful retry;
- `2`: concurrency refusal;
- `3`: collection or completeness failure that prevents a valid cycle;
- `4`: continuity conflict/failure;
- `5`: Dedup failure;
- `6`: Premium failure;
- `7`: Dashboard incompatibility/failure;
- `8`: readiness failure;
- `9`: invalid configuration, cohort, retry, or stale-cycle state.

JSON output always includes authorization separately; non-authorization alone never changes exit
code zero.

## 13. Alerts and known blockers

Operational alerts are append-only and bounded. Codes include `CYCLE_FAILED`,
`SOURCE_DEGRADED`, `SOURCE_RECOVERED_OPERATIONALLY`, `SOURCE_INCOMPLETE`,
`FRESHNESS_APPROACHING`, `FRESHNESS_EXPIRED`, `CONTINUITY_CONFLICT`,
`DASHBOARD_BUILD_FAILED`, `AUTHORIZATION_CHANGED`, `ELIGIBLE_SOURCE_COUNT_CHANGED`,
`IMPLEMENTED_COHORT_CHANGED`, `BLOCKED_SOURCE_SELECTED`, `STALE_CYCLE_DETECTED`, and
`BACKUP_FAILED`.

Each event pins cycle, time, severity, code, affected Source/artifact where applicable, and bounded
detail without job descriptions, contact data, private addresses, credentials, or secrets.

The unchanged known structural deficit `20/29 < 24/29` is persisted as an authorization blocker but
does not emit a new emergency alert every cycle. Authorization transition alerts are emitted only
when the state changes relative to the preceding successful cycle.

## 14. Status surface

`observatory_status --json` derives only from persisted cycle evidence and reports latest cycle,
last successful cycle, cycle age, cohort and Source health/completeness/freshness, failed/degraded
Sources, eligible Sources, critical reviews, authorization, headline availability, and PIT cutoff.
It is read-only and deterministic for unchanged evidence. No public endpoint starts a cycle.

## 15. History and cadence

Intended cadence is one governed FULL_SOURCE cycle per calendar day inside an externally configured
operational window. The repository does not fix a wall-clock time. cron, systemd, Windows Task
Scheduler, or another external scheduler invokes exactly one command; Django contains no hidden
daemon.

Every successful production-intended cycle accumulates immutable PIT history. `PIT_HISTORY_START`
is the first successful cycle completed after GATE-012 implementation. Older gate artifacts remain
historical scientific evidence but are not relabeled. A missed day records an operational gap when
observed; it never creates a synthetic cycle or backdated observation.

CollectionRuns, observations, lifecycle events, continuity applications, DedupRuns, Premium runs,
Dashboard snapshots, readiness assessments, cycles, attempts, and events are retained. GATE-012
defines no destructive retention or RAW deletion policy. Thirty real days is a later program
milestone, not a PR acceptance wait.

## 16. Scheduler, timeout, logging, and security

Scheduling is external. The command accepts a bounded whole-cycle timeout and updates a heartbeat at
stage boundaries. It writes structured logs carrying `cycle_id`, `stage`, and Source ID where
applicable. It never logs full descriptions, contact/private evidence, secrets, or credentials.

The orchestrator accepts Source identity only from the governed registry/cohort, never arbitrary
URLs or shell commands. Execution remains a management command and is not exposed publicly.

## 17. Backup and restore boundary

Database backup is an external, credential-free hook/procedure independent of a cycle. Acceptance
evidence records timestamp, target identifier, command result, and integrity proof. Restore smoke
testing uses an isolated database and reads the latest cycle and pinned artifacts; it never restores
over the operational database. Infrastructure-grade disaster recovery and destructive retention are
future gates.

## 18. Failure and acceptance requirements

Tests must cover blocked-before-HTTP selection, real concurrency refusal, interruption after partial
collection and after collection/before downstream, retry idempotence, source HTTP failure,
incomplete Source, continuity conflict, Dedup failure, Dashboard incompatibility, authorization
transitions, deterministic status JSON, immutable cycle N after N+1, no synthetic missed cycle, and
no alert spam for unchanged structural coverage.

Live acceptance runs one full production-like cycle over the governed implemented cohort with zero
blocked Source requests, records source runtimes and aligned final artifacts, and proves exact retry
and downstream replay without an unnecessary second network refresh.
