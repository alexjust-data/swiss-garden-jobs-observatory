# Decision 0015: GATE-011D Day-0 authorization policy

## Status

Accepted. Current assessment is **DAY_0_NOT_AUTHORIZED**.

## Baseline

Merged GATE-011C-6 baseline: `a9199cac3cc0233adf7b523fd9671e19981c5822`.

## Decision

Coverage policy `day0-coverage-v0.1` requires 24/29 fresh, healthy, complete required Sources, with minima of federal 1/1, canton 15/22, and city 4/6. Freshness policy `full-source-freshness-v0.1` uses `CollectionRun.finished_at` and an inclusive 72-hour wall-clock maximum age. Authorization policy is `day0-authorization-v0.1`; readiness evidence is `day0-readiness-v0.3`.

All 29 Sources require final disposition. The nine C-6 blocked Sources remain in the denominator and appear as not covered; their blocker class is explanatory, not an exemption or automatic veto. A fresh healthy complete zero-result run counts as covered.

The latest accepted complete FULL_SOURCE run supplies immutable source evidence. Later failed/outage/degraded activity preserves that evidence but fails current health. Policy values, policy versions, source evidence, aligned downstream IDs, review sets, and cutoff participate in the readiness fingerprint.

Closed GATE-011A critical-review semantics remain intact: reviews capable of changing the public count or identity block authorization. Green `REVIEW` remains non-public.

## Current result

At `2026-08-12T07:30:00Z`, disposition is 29/29, but only 18/29 Sources are fresh and eligible. Structural coverage is federal 1, canton 13, city 4. Winterthur and Z?rich are stale at approximately 87.5 and 87.4 hours. Coverage fails 24/29; cantons fail 15/22; 53 critical green reviews also remain. Result: `DAY_0_NOT_AUTHORIZED`.

The numeric value remains null in the public market-figure API. The 14 green-confirmed records are corpus diagnostics, not an authorized headline.

## Future versions

Policies are append-only and versioned. A future policy change creates a new fingerprint and assessment and cannot rewrite historical assessments. Every future snapshot is evaluated independently. No source, dedup, green, employer, geography, robots, or acquisition semantics change in this decision.
