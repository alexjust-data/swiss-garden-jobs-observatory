# ADR 0020: governed daily Observatory Cycle

Status: Proposed for GATE-012 acceptance

Baseline: merged GATE-011G `3f8e5cacc191309188e142ebf28ae0d1115e95e7`  
Operating-contract commit: `f2b77eeb5e8514d6a972c3ae95d85b12aab3b22e`

## Context and decision

The observatory's scientific layers were independently accepted, but daily execution still required
a human to order collection, continuity, Dedup, Premium, Dashboard, and readiness. Introduce
`daily-observatory-cycle-v0.1`, `run_daily_observatory`, and read-only `observatory_status`.

The cohort is derived from the frozen Day-0 universe and C-6 dispositions. PostgreSQL advisory
locking occurs before collector construction. Source attempts and operational events are append-only;
a successful cycle becomes immutable and pins all four aligned PIT artifacts. Same-cycle retry
returns a successful stored result without network; explicit recovery preserves previous attempts.

The cutoff follows green continuity. Dedup first establishes any material-identical inherited
authority; when this creates new applications, the final cutoff advances and a final aligned Dedup
run is built before Premium, Dashboard, and readiness. Existing scientific services remain the sole
owners of their semantics and fail-closed validation.

Operational health (`GREEN/AMBER/RED`) and Day-0 authorization are separate. A healthy 20-Source
cycle may be `SUCCEEDED_NOT_AUTHORIZED` because 20/29 remains below 24/29. Stable exit zero reflects
technical success, not permission to publish the headline.

Scheduling and backups stay external and replaceable. Every real successful cycle accumulates PIT
history; missed days are not synthesized and no historical evidence is deleted.

## Preserved contracts

GATE-012 does not change frozen research, green classifier/review/material semantics,
`dedup-v0.1`, dedup continuity, Premium, coverage/freshness/authorization, geography, blocked-source
dispositions, or Job-Room. Live acceptance, backup/restore evidence, exact artifacts, and validation
results are appended after execution; the operating contract itself remains unchanged.
