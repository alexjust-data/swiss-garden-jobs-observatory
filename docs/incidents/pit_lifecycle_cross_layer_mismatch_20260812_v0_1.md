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

Lifecycle chronology is canonical everywhere as `(observed_at, created_at, pk)`. Equal source timestamps are resolved by immutable creation time before UUID; Dedup status/episodes and Premium cannot choose different latest events.

`NOT_FOUND` is lifecycle evidence and never classification content. Pending and closed Postings retain their last valid content for identity, classification, provenance, and historical presentation. Lifecycle remains authoritative for current economic state. `DISAPPEARED_PENDING` does not close a Vacancy; `CLOSED_OBSERVED` does. Reappearance selects the new active observation.

Premium fingerprints the selected observation, latest lifecycle event and state, and PIT-selection version. Dashboard continues to require exact Dedup/Premium observation-ID equality and rejects Premium runs without the supported PIT-selection version. Day-0 market metrics and authorization-critical reviews require an `ACTIVE` run-scoped Vacancy.

Dedup review criticality is based on possible effect on at least one eligible active public-capable Vacancy. An ACTIVE/CLOSED pair is therefore critical when the active side is GREEN or REVIEW: a human merge can change economic identity, canonical evidence, or active status even though the other side is closed. Closed-only pairs, and ACTIVE NOT_GREEN versus CLOSED GREEN where no possible active public member exists, remain noncritical.

## Corrected live evidence

The preserved incident database was copied before corrective derivation. Experimental, unmerged 011E schema objects were removed only from the copy; immutable observations, lifecycle events, and collection runs were unchanged.

| Artifact | ID | Fingerprint / result |
|---|---|---|
| DedupRun | `0f241f99-b1da-4c99-8d44-5d5d992e9f88` | `3dbd2aff9933a1eb84370325b5f04e071ca4b1c07377377164dd5f84bb9c71b2` |
| PremiumSegmentRun | `27a26441-80e8-48a0-8680-42fa035e8287` | `df12c53075614cc610ee7d6d8bac4503797e13394539a9edde537ff45ead1c8b` |
| DashboardSnapshot | `58293afa-1f08-4e48-a769-6344888baaa6` | `9569643c2a83d1109a7a236a9260b6ec2ea9a059a24139f5364b345030f8e28d` |
| Day0ReadinessAssessment | `ee972d80-fe6e-47fb-8e62-001e5028abd5` | `9cc198fdb18e19c645b6cbb1357021098107e1d7a04df2577aabecd6e958ef3e`; blocked by data quality |

Corrected Dedup and Premium each contain 1,971 exact observation IDs. Both set differences are empty. Dashboard construction succeeds. Identical replay reuses all corrected derived artifacts. No review was adjudicated; the corrected cohort logic exposes 55 critical green reviews and one critical dedup review, and Day-0 remains unauthorized.
