# Review authority database lineage break -- 2026-08-13

Status: open corrective incident under GATE-011G-C1
Affected operational cycle: `be7062f8-f587-4e96-aef2-bc4caa1142e2`
Corrective baseline: `520b68d989d36abfc382143458b30d1f3bad96b2`

## Incident summary

The first suspended GATE-012 operational cycle completed its governed pipeline against the
authority evidence actually present in the operational database. That database did not contain
the human review authority established by GATE-011E, so GATE-011G continuity could not inherit
that knowledge. GATE-012 stopped instead of manufacturing decisions or copying rows manually.

This incident is a database-lineage break. It is not evidence that the previously reviewed jobs
became scientifically uncertain again, and it is not evidence that every unmatched current
assessment is materially equivalent to an earlier reviewed assessment.

## Immutable affected cycle

| Field | Recorded value |
|---|---:|
| Cycle | `be7062f8-f587-4e96-aef2-bc4caa1142e2` |
| Status | `SUCCEEDED_NOT_AUTHORIZED` |
| Cutoff | `2026-08-13T16:37:37.237172Z` |
| Sources attempted | 20 |
| Successful | 19 |
| Failed Source | `SRC-OFF-CANTON-TG` |
| Blocked Sources requested | 0 |
| Eligible Sources | 19 / 29 |
| Active GREEN | 14 |
| Critical green reviews | 55 |
| Critical dedup reviews | 1 |
| Day-0 | `DAY_0_BLOCKED_BY_DATA_QUALITY` |
| Headline | `null` |

The cycle and all pinned collection and downstream artifacts remain immutable. C1 will not change
its status, cutoff, evidence, or results.

## Observed authority state

The following counts were measured before C1 reconciliation. They are observations requiring
row-level verification, not authority merely because of a database name.

| Evidence | Operational `swiss_garden_jobs` | Historical evidence source `swiss_garden_jobs_gate011e_contract` |
|---|---:|---:|
| Green human decisions | 0 | 55 |
| Green continuity applications | 0 | 185 |
| HUMAN dedup decisions | 0 | 1 |
| Dedup continuity applications | 0 | 5 |

The historical green outcomes observed were 37 `CONFIRMED_GREEN`, 16
`CONFIRMED_NOT_GREEN`, and 2 `INSUFFICIENT_EVIDENCE`. These aggregates must be reconciled
item-by-item against merged GATE-011E governance before any import is permitted.

## Continuity symptom

The affected cycle recorded green continuity as:

```text
created       0
reused        0
unmatched   237
conflicts     0
```

`unmatched = 237` describes the operational database's knowledge at that time. It must not be
relabelled as 237 new scientific review questions, and C1 must not target zero unmatched items.
Only identical governed identity plus identical frozen material evidence may inherit prior human
authority.

## Corrective boundary

C1 audits the historical source read-only, proves the irreducible 55 green decisions and one
dedup decision against merged governance, and tests exact transplantation on an isolated copy of
the operational database. Human decision identity and timestamps must be preserved. Derived
continuity applications may be imported only with exact dependency identity; otherwise later
applications must be regenerated against target evidence. No application may be retargeted.

The real operational database remains unchanged before independent audit and merge. No Source
HTTP request and no new human adjudication are part of this correction.
