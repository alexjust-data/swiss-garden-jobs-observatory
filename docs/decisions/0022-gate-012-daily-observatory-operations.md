# ADR 0022: governed daily Observatory Cycle

Status: Accepted for GATE-012 implementation audit

Scientific baseline: merged GATE-011G `3f8e5cacc191309188e142ebf28ae0d1115e95e7`
Operational resumption baseline: merged GATE-011G-C1 `56db937626a38bcbfe8eee6f4653386a24b14d08`
Operating-contract commit: `f2b77eeb5e8514d6a972c3ae95d85b12aab3b22e`

## Context and decision

The observatory's scientific layers were independently accepted, but daily execution still required
a human to order collection, continuity, Dedup, Premium, Dashboard, and readiness. Introduce
`daily-observatory-cycle-v0.1`, `run_daily_observatory`, and read-only `observatory_status`.

The cohort is derived from the frozen Day-0 universe and C-6 dispositions. PostgreSQL advisory
locking occurs before collector construction. Source attempts and operational events are append-only;
a successful cycle becomes immutable and pins all four aligned PIT artifacts. Same-cycle retry
returns a successful stored result without network; explicit recovery preserves previous attempts.

The cutoff follows green continuity. Dedup establishes material-identical inherited authority and the
final aligned Dedup run is built before Premium, Dashboard, and readiness. Existing scientific
services remain the sole owners of their semantics and fail-closed validation.

Operational health (`GREEN/AMBER/RED`) and Day-0 authorization are separate. A cycle can be
`SUCCEEDED_NOT_AUTHORIZED`; stable exit zero reflects technical success, not permission to publish
the headline. Scheduling and backups stay external and replaceable. Every real successful cycle
accumulates PIT history; missed days are not synthesized and no historical evidence is deleted.

## Corrective-gate integration

GATE-012 was suspended when its first real cycle exposed absent review authority and a historical
Day-0 policy-artifact collision. GATE-011D-C2 and GATE-011G-C1 corrected those defects on main.
Resumption preserved the predeclared operating contract and merged corrected main into the existing
branch. The canonical C1 `observations.0012_review_authority_schema_reconciliation` migration
superseded the narrower unmerged GATE-012 repair migration; no scientific contract changed.

ADR number 0022 is used because merged corrective gates C2 and C1 occupy ADRs 0020 and 0021.

## Live acceptance

Cycle `72630745-5100-4f63-92b9-d8e2e35c2a0b` ran from
`2026-08-13T23:07:24.699745Z` to `2026-08-14T00:12:12.576783Z`, selected the 20 governed
implemented Sources and selected zero blocked Sources. Nineteen Sources were healthy, complete and
counter-consistent. Thurgau failed closed because its surface total changed during pagination; the
failure created no false CollectionRun and no negative lifecycle evidence.

Green continuity created 156 applications, reused 70 exact historical applications, left eight
unmatched, and found zero conflicts. Dedup continuity created two applications. The final aligned
cutoff was `2026-08-14T00:07:17.897427Z`.

The pinned artifacts are:

- DedupRun `5b1113a9-b3e7-4dcc-a34f-759a2bb1cc5b`, fingerprint
  `b8f2ab74b4c321916b253f3397b88d81cc5eaee3e03129219cb11dbe1e7d7252`;
- PremiumSegmentRun `641fbb6c-25f0-451e-91c2-e3197be4a9d7`, fingerprint
  `0a49c84401bcc5804c34573bcaa352fb4f61323420731a0576a608ee3856c35d`;
- DashboardSnapshot `0796b785-4da6-488e-b114-674e4209b6e4`, fingerprint
  `22cd7a1670427b485387ba7cbf6f0471a101c588251544cae69919abac1a6bc9`;
- Day0ReadinessAssessment `542b36ad-7e33-4b22-8019-930df6c5eae8`, fingerprint
  `62474a2b3fbeda641e2fe743a53c756a426ec18833703611792e3706bd8b50e3`.

Each fingerprint has one artifact. Exact same-cycle retry returned these IDs in 1.5 seconds with
`exact_cycle_retry_reused=true` and no Source HTTP.

The accepted result is operational health `AMBER`, 19/29 eligible Sources, 51 active confirmed-green
Vacancies, three critical green reviews, zero critical dedup reviews, and
`DAY_0_BLOCKED_BY_DATA_QUALITY` with a null headline. The cycle is operationally successful; it does
not weaken the 24/29 authorization threshold.

Full pytest passed 433 tests; focused GATE-012 passed 18; Playwright passed its Chromium acceptance.
Ruff, mypy, Django check and migration-drift checks passed. Existing and clean PostgreSQL paths both
passed migration and double reference-import validation.

A PostgreSQL 16 custom backup of the post-cycle database had SHA-256
`3ecccb748ba20c29d6793872fb426562d864e6f6bcc7deed4555190ec865bfb4`. It restored into an isolated
database, passed Django and reference checks, and reproduced the accepted cycle plus its four pinned
artifacts without altering the operational database.

## Preservation

GATE-012 does not change frozen research, green classifier/review/material semantics,
`dedup-v0.1`, dedup continuity, Premium, coverage/freshness/authorization, geography, blocked-source
dispositions, or Job-Room. The operating contract remains byte-identical to its isolated commit.
