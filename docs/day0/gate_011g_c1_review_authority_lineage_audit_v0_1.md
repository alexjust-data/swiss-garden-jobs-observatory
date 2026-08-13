# GATE-011G-C1 review authority database lineage audit v0.1

Baseline: `520b68d989d36abfc382143458b30d1f3bad96b2`
Contract-only commit: `4b8ba079b2ca57ed8f0c2ae696e7edd6bfd7f519`
Lineage version: `review-authority-lineage-v0.1`

## Suspended operational evidence

GATE-012 remains suspended. Cycle `be7062f8-f587-4e96-aef2-bc4caa1142e2` is unchanged at
cutoff `2026-08-13T16:37:37.237172Z`. It remains valid evidence of an operational run whose
database contained no replicated human authority. C1 did not alter that cycle or any pinned
artifact.

## Coherent source snapshot

Logical source: historical governed evidence database
Access: PostgreSQL `REPEATABLE READ` plus `READ ONLY`
Schema migrations executed against source: 0
Snapshot fingerprint: `4347bd138b4d26378277d5c29bea5702c9fdb8cfa95ea5be3593dfc727304dc5`

The database name was not treated as authority. Every green row was reconciled mechanically
against `docs/day0/gate_011e_critical_review_resolution_v0_1.md`. The dedup authority was
reconstructed through its source algorithm decision and exact historical PIT evidence.

## Authority registry and package

Registry: `docs/day0/gate_011g_c1_review_authority_registry_v0_1.json`
Registry version: `review-authority-registry-v0.1`
Package SHA-256: `cd08a0aa22c93177a6181211fab1d17f653bbe8233ff52e76d76f692aceb6bdd`
Package storage: local governed acceptance artifact; intentionally not committed because it
contains complete decision evidence and dependency rows.

Merged governance pinned by the package:

- GATE-011E: `cbf1054b329843ea3fff7eeac77ea9342df60147`
- GATE-011G: `3f8e5cacc191309188e142ebf28ae0d1115e95e7`
- C1 baseline: `520b68d989d36abfc382143458b30d1f3bad96b2`

Each package row has a canonical SHA-256. The registry additionally pins full row hashes for the
human decision and its reviewed assessment/observation, or the human dedup decision and its
algorithm/run. Changing an outcome, evidence value, dependency, relationship, or supported model
invalidates verification.

## Irreducible authority

| Authority | Count | Reconciliation |
|---|---:|---|
| Green `CONFIRMED_GREEN` | 37 | 37/37 exact merged IDs and provenance |
| Green `CONFIRMED_NOT_GREEN` | 16 | 16/16 exact merged IDs and provenance |
| Green `INSUFFICIENT_EVIDENCE` | 2 | 2/2 exact merged IDs and provenance |
| Dedup HUMAN `KEEP_SEPARATE` | 1 | exact UUID and reconstructed material |

Dedup authority UUID: `74550a24-4075-469c-946a-4ea48c045877`
Source algorithm decision: `bb37c095-9591-4920-84b7-2d0b69b3e98b`
Source DedupRun: `0f241f99-b1da-4c99-8d44-5d5d992e9f88`
Source cutoff: `2026-08-12T10:20:02.339073Z`
Material fingerprint: `c9f0c0f6a4c0d57062bd15b8024dd434bee2d889a531b74d950277e77d518087`

## Dependency compatibility

All 55 reviewed `GreenRelevanceAssessment` IDs, their 55 `PostingObservation` IDs, RAW IDs,
and collection evidence already existed identically in the operational target. Posting projection
rows had legitimately evolved after later cycles; no Posting, acquisition, RAW, collection, or
lifecycle row was imported or rewritten.

The dedup source `DedupRun` and algorithm decision were absent without PK or natural-key
collision. Their two exact PIT observations and lifecycle selection already existed identically in
the target. These two bounded derived dependencies were therefore imported with original IDs and
timestamps before the human dedup decision. Target reconstruction produced the same `c9f0--8087`
material fingerprint.

Compatibility result:

| Class | Present identical | Absent importable | Regenerate | Conflict |
|---|---:|---:|---:|---:|
| Green human authority | 0 | 55 | 0 | 0 |
| Dedup human authority | 0 | 1 | 0 | 0 |
| Dedup authority dependencies | 0 | 2 | 0 | 0 |
| Historical green applications | 0 | 70 | 115 | 0 |
| Historical dedup applications | 0 | 0 | 5 | 0 |

No historical application was retargeted. Applications classified `Regenerate` remained in the
source package and could only be recreated by normal 011G logic against exact target evidence.

## Target schema audit

The historical source table matched merged model fields. The operational database contained one
extra physical `reviewed_by varchar NOT NULL` column left by an older development schema. It had
zero rows, but prevented exact inserts. The suspended GATE-012 migration had repaired earlier
column/constraint drift but did not remove this column.

C1 independently introduces
`observations.0012_review_authority_schema_reconciliation`. It removes `reviewed_by` only when
the decision table is empty. If any row exists, migration fails with
`EXACT_AUTHORITY_TRANSPLANT_NOT_POSSIBLE` instead of discarding reviewer provenance.

The source algorithm also contained the scientifically valid value `hard_barriers=[]`. Django
model validation had not declared empty JSON lists as valid. C1 makes that existing semantic
truth explicit with `blank=True`; it does not change dedup scoring or thresholds.

Both issues were found in isolated acceptance. The failed dry runs rolled back completely.

## Isolated target import

Target: isolated copy of the real operational database
Target prestate fingerprint: `b7af2c0bd2a6986cefd1392f2996f9bf0ddebe988af457e85cb4cb4a718e5f48`
Lineage batch: `dcae96c3-e538-41f9-baaf-4e43e698c102`
Replicated at: `2026-08-13T18:04:56.997722Z`
Batch input fingerprint: `e8cc227923c2b33279f6f33080b35645af52ca74cc437e61ef4b565ce17dca83`

Import result:

- green human decisions imported: 55;
- dedup human decisions imported: 1;
- bounded dedup dependencies imported: 2;
- exact green applications imported: 70;
- exact dedup applications imported: 0;
- new human decisions created: 0;
- conflicts: 0.

The exact package was imported twice. The second execution reused the same lineage batch and
created zero human decisions, dependencies, or applications.

## Target continuity

After authority import, normal 011G continuity evaluated current operational evidence:

- historical exact green applications imported: 70;
- new target green applications created: 105;
- total green applications causally available at final cutoff: 175;
- unmatched REVIEW assessments: 7;
- unmatched from a new Posting identity: 2 assessments for `SRC-OFF-CANTON-GR / 2810`;
- unmatched after material change to a previously reviewed Posting: 5 assessments;
- no human decisions created.

The five changed assessments belong to `SRC-OFF-JOBS-ADMIN / 10140947` (three observations) and
`SRC-OFF-CITY-BERN / 10144087` (two observations). No prior outcome was reused.

The two original insufficient decisions remain authorization-critical REVIEW for current exact
material:

- `6d40da88-f664-4e51-ba5f-9b2413426e6c` -- AR / `3996438`;
- `60cf7b46-ab36-410a-becb-c1b4af88d15a` -- SG / `6251`.

Dedup continuity initially exposed an engine lookup defect: legacy authority without a stored
011G material fingerprint was reconstructable but excluded by the database filter. C1 now selects
causal HUMAN decisions for the exact unordered pair and independently reconstructs material.
Multiple matching human decisions fail closed. The corrected engine created target applications
for the Brugg/Emmen algorithm evidence; no new human decision was created.

## Corrected PIT chain

Final cutoff: `2026-08-13T18:18:31.708951Z`

| Artifact | ID | Input fingerprint |
|---|---|---|
| DedupRun | `df796844-4153-4913-b2a9-96b6aa97fbf9` | `628bd36fd0e53ffea255bfb7039832239658e07271ba1abaf87ff5a47b42fcd1` |
| PremiumSegmentRun | `932399ea-bd99-444b-a2f6-0bd54149f9ca` | `10be60934afcc36230538afc7ec5d7d1ddce39d8bb7dff8afefea7a7513a8c47` |
| DashboardSnapshot | `17d36a7c-ebd4-4aa1-a664-576ccf32a870` | `4aa9843b416b24d3720e2610b0139017928d8dccf30924cf881a9e2c03212ad8` |
| Day0ReadinessAssessment | `41c1c488-e0ee-405d-8d00-19685be21bcb` | `489046ae63bf695b5988f225d9440aed640f305b8ae4c5d58c24a43d64ef99c0` |

Final evidence:

- required Sources: 29;
- implemented Sources: 20;
- acquisition-eligible at cutoff: 19 (TG's failed GATE-012 attempt remains current activity);
- fresh evidence: 20;
- active GREEN: 51;
- critical green reviews: 3;
- critical dedup reviews: 0;
- Day-0: `DAY_0_BLOCKED_BY_DATA_QUALITY`;
- headline: `null`.

The three critical green reviews are the two preserved insufficient decisions and the new
`SRC-OFF-CANTON-GR / 2810` Posting. Coverage remains below 24/29 independently of review state.

## Exact replay

The exact final cutoff was repeated. Dedup, Premium, Dashboard and Readiness each returned the
same ID and fingerprint with `reused=true`. Exactly one artifact exists for each fingerprint.

## Real database boundary

The real `swiss_garden_jobs` database was not migrated and received no authority package during
C1 development or acceptance. Post-merge application requires backup, preflight, zero conflicts,
exact package import, idempotent replay, and verification before GATE-012 resumes.

## Final local validation

- `pytest -q`: 409 passed;
- focused C1 plus dedup PIT reconciliation: 26 passed;
- Playwright browser acceptance: 1 passed;
- Ruff: passed;
- mypy: no issues in 145 source files;
- Django system check: passed;
- migration drift: none;
- PostgreSQL clean migration: passed;
- PostgreSQL isolated operational-copy migration/import: passed;
- reference import twice on clean and existing-copy databases: passed;
- repeated read-only export: same package and snapshot fingerprints;
- exact package dry-run and repeated import: same lineage batch, zero new rows;
- real operational database modified before merge: no.
