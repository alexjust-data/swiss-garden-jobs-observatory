# Decision 0007: GATE-011A Day-0 coverage and authorization contract

## Status

Accepted for implementation. It does not authorize Day-0.

## Decision

Day-0 readiness is an immutable, point-in-time assessment over an explicit governed source universe. Coverage means completion of that expected source universe; it is not an estimate of the unknowable number of jobs in the true market.

The initial universe is `day0-source-universe-v0.1`. Its required denominator contains the official federal employment portal, the German-speaking canton portals represented in frozen v0.4, and the six priority central city portals for Zurich, Winterthur, Bern, Luzern, St. Gallen, and Schaffhausen. Sector, public-discovery, specialist-green, and P1 staffing sources are supporting. Lower-priority general and regional sources are deferred. Reference, statistical, publishing-only, and salary sources are not applicable.

Target role and operational access state are separate. A required source with unresolved automation or legal review remains in the required denominator and is classified `BLOCKED_PENDING_ACCESS_REVIEW`; it is not silently removed to improve coverage.

## Completion and denominator semantics

A required source counts as complete only when the selected PIT run is `FULL_SOURCE`, `SUCCEEDED`, `HEALTHY`, pagination/snapshot completeness is proven, and listing, observation, and green-assessment counts agree. A healthy complete source with zero qualifying jobs is covered and contributes an observed zero. A geography without a completed required source is `NOT_COVERED`, never zero demand.

Every coverage metric persists its numerator, denominator, definition, metric version, and exact evidence IDs. The dimensions are required-run, health, canonical-source, governed geography, publication date, safe geospatial presentation, green classification, dedup quality, position disclosure, and source-link provenance.

## Threshold policy

Frozen v0.4 does not authorize a numeric Day-0 source-completion threshold. The operational policy `day0-authorization-policy-proposed-v0.1` therefore remains pending. Independent review must choose among consequences such as 100%, at least 95%, or at least 90% completion; implementation must not choose a threshold to fit current data. While pending, readiness is `DAY_0_THRESHOLD_POLICY_PENDING`.

## PIT authority and reviews

`Day0ReadinessAssessment` references one exact `as_of`, source universe, `DedupRun`, `PremiumSegmentRun`, `DashboardSnapshot`, selected source runs, metrics, review IDs, blockers, and input fingerprint. Later source runs, reviews, dashboards, or derived evidence cannot change an existing assessment.

Reviews are critical when they can change the public Day-0 vacancy count or identity, including public-cohort dedup ambiguity, green-review candidates, missing green evidence, public geospatial review, or public premium review. Other reviews remain visible as noncritical. GATE-011A does not resolve reviews.

## Market-state schema

Future GATE-011D may publish only an authorized state containing separate observed postings, active unique vacancies, known positions, unknown-position vacancy count, multi-hire count, new/reappeared/closed-observed vacancies, unique employers/agencies, coverage metrics, critical review count, and authorization status. Missing position count is never defaulted to one. Vacancy counts alone do not establish labour shortage or nationwide completeness.

## Current conclusion and expansion sequence

The current two-source implementation is expected to remain not ready. Expansion is ordered as:

1. Reusable priority-city platform sources and access decisions.
2. Remaining official federal and German-speaking canton P0 canonical portals.
3. Sector, specialist-green, and public-discovery supporting coverage.
4. Governed staffing/private-market supporting coverage.

Actual reconnaissance and collectors belong to GATE-011B. This decision adds no network access, collection, geocoding, reclassification, scheduler, market number, or changes to frozen research or closed-gate semantics.
