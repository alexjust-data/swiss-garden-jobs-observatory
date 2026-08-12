# Decision 0015: GATE-011D Day-0 authorization policy

## Status

Accepted. Current assessment is **DAY_0_NOT_AUTHORIZED**.

## Baseline

Merged GATE-011C-6 baseline: `a9199cac3cc0233adf7b523fd9671e19981c5822`.

## Decision

Coverage policy `day0-coverage-v0.1` requires ratio >=0.80: with 29 discrete Sources, 23/29 fails and 24/29 (82.76%) passes. Structural minima are federal 1/1 and city 4/6; passing total plus federal derives a canton floor of 17/22. Freshness policy `full-source-freshness-v0.1` uses `CollectionRun.finished_at` and an inclusive 72-hour wall-clock maximum age. Authorization policy is `day0-authorization-v0.1`; readiness evidence is `day0-readiness-v0.3`.

All 29 Sources require final disposition. The nine C-6 blocked Sources remain in the denominator and appear as not covered; their blocker class is explanatory, not an exemption or automatic veto. A fresh healthy complete zero-result run counts as covered.

The latest accepted `FULL_SOURCE + SUCCEEDED + HEALTHY + complete` run supplies immutable source evidence. Later failed/outage/degraded activity preserves that evidence but fails current health. Policy values, policy versions, exact eligible Source IDs, filtered market state, aligned downstream IDs, review sets, and cutoff participate in the readiness fingerprint.

The public `coverage.eligible` count is the cardinality of that exact eligible Source set, not the broader number of fresh accepted FULL_SOURCE runs. The latter remains separately disclosed as `coverage.freshness_valid`, because a later outage may preserve fresh evidence while invalidating current eligibility.

Counts below 29 for complete or currently healthy required Sources remain transparent readiness diagnostics and coverage-metric inputs. They are not independent authorization failures under a policy that explicitly permits 24/29 coverage. The exact readiness API separates effective `authorization_failures` from denominator-only or diagnostic evidence.

Closed GATE-011A critical-review semantics remain intact: only reviews capable of changing the eligible Day-0 count or identity block authorization. Reviews from blocked, stale, unhealthy, incomplete, supporting, or otherwise excluded Sources remain visible as noncritical evidence. Green `REVIEW` remains non-public.

## Current result

The current corrected PIT audit is rebuilt below. Authorization-facing market metrics use only dashboard records whose canonical observation Source is in the exact eligible Source set. Supporting provenance cannot re-canonicalize an excluded record in v0.1.

Exact DashboardSnapshot endpoints remain immutable and contain no dynamically selected readiness assessment. Exact readiness endpoints are pinned by assessment ID; the current convenience endpoint declares its selection policy. Unauthorized market value remains null.

## Future versions

Policies are append-only and versioned. A future policy change creates a new fingerprint and assessment and cannot rewrite historical assessments. Every future snapshot is evaluated independently. No source, dedup, green, employer, geography, robots, or acquisition semantics change in this decision.
