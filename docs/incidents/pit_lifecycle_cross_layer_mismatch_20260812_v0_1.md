# PIT lifecycle cross-layer mismatch — 2026-08-12

## Incident

At cutoff `2026-08-12T10:20:02.339073Z`, after the governed refresh of all 20 implemented required Sources, aligned derivation failed closed:

| Evidence universe | Count |
|---|---:|
| Dedup selected observations | 1,971 |
| Premium assessments | 1,889 |
| Dedup minus Premium | 82 |
| Premium minus Dedup | 0 |

Every missing Premium row had a prior `ACTIVE` `PostingObservation` and a latest `DISAPPEARED_PENDING` lifecycle event. The affected Sources were Stadt Zürich (19), Federal (16), Kanton Zürich (13), Winterthur (10), Basel-Landschaft (4), Stadt Luzern (4), Schwyz (3), Basel-Stadt (3), Thurgau (2), St. Gallen (2), Appenzell Ausserrhoden (2), Stadt Bern (2), Luzern (1), and Stadt Schaffhausen (1).

The 20-source refresh itself was valid: 20 runs succeeded, were healthy, and were complete; no C-6 blocked Source was requested. Its window was `2026-08-12T08:45:21Z` through `2026-08-12T09:41:46Z`.

## Root cause

GATE-008 selected the last `ACTIVE` content observation independently of later lifecycle evidence. GATE-009 instead removed a Posting at both `DISAPPEARED_PENDING` and `CLOSED_OBSERVED`. GATE-010 correctly rejected the resulting unequal observation-ID universes.

The collection evidence is valid. A first healthy absence is deliberately `DISAPPEARED_PENDING`, not closure; the immutable `NOT_FOUND` observation and lifecycle event must remain. The defect was the cross-layer interpretation of that evidence.

## Corrected contract

`posting-pit-selection-v0.1` derives, independently at cutoff T:

- the latest `ACTIVE` content observation at or before T;
- the latest lifecycle event at or before T.

`NOT_FOUND` is lifecycle evidence and never classification content. Pending and closed Postings retain their last valid content for identity, classification, provenance, and historical presentation. Lifecycle remains authoritative for current economic state. `DISAPPEARED_PENDING` does not close a Vacancy; `CLOSED_OBSERVED` does. Reappearance selects the new active observation.

Premium fingerprints the selected observation, latest lifecycle event and state, and PIT-selection version. Dashboard continues to require exact Dedup/Premium observation-ID equality and rejects Premium runs without the supported PIT-selection version. Day-0 market metrics and authorization-critical reviews require an `ACTIVE` run-scoped Vacancy.

## Corrected live evidence

The preserved incident database was copied before corrective derivation. Experimental, unmerged 011E schema objects were removed only from the copy; immutable observations, lifecycle events, and collection runs were unchanged.

| Artifact | ID | Fingerprint / result |
|---|---|---|
| DedupRun | `bfa5f769-ee34-480e-a935-103ad17b66ce` | reused; `78d7a66e747e5053c01bc885dc05fddf2ac87c235f91efe028c685907baec1eb` |
| PremiumSegmentRun | `27a26441-80e8-48a0-8680-42fa035e8287` | `df12c53075614cc610ee7d6d8bac4503797e13394539a9edde537ff45ead1c8b` |
| DashboardSnapshot | `048dedf2-bc1b-4191-8f1c-08cf768fdf2a` | `77a2bbec78f74027695dcc1d14d0f70fa4acd5ff6a1eb1117c04c7b5eeb81929` |
| Day0ReadinessAssessment | `9c0e6f80-e5d6-4026-8ecd-1e591be0e74f` | `d2467e5decc34c3339b75a3abe05342abad3503f16013169f479d99ea286e330`; blocked by data quality |

Corrected Dedup and Premium each contain 1,971 exact observation IDs. Both set differences are empty. Dashboard construction succeeds. Identical replay reuses all corrected derived artifacts. No review was adjudicated and Day-0 remains unauthorized.
