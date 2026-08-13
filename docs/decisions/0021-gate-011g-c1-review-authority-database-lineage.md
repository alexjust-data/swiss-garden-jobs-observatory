# ADR 0021 -- GATE-011G-C1 review authority database lineage

Status: proposed for independent audit
Baseline: `520b68d989d36abfc382143458b30d1f3bad96b2`
Contract commit: `4b8ba079b2ca57ed8f0c2ae696e7edd6bfd7f519`

## Context

Suspended GATE-012 cycle `be7062f8-f587-4e96-aef2-bc4caa1142e2` proved that the operational
database contained no GATE-011E human review decisions. Collection and downstream orchestration
worked, but continuity correctly reported no inherited knowledge. The cycle remains immutable.

The historical evidence database contains 55 green human decisions and one dedup human
`KEEP_SEPARATE`. Its name does not grant authority. Merged GATE-011E governance and exact
evidence lineage do.

## Decision

Adopt `review-authority-lineage-v0.1` as a deterministic portability mechanism with:

1. a PostgreSQL repeatable-read, read-only export;
2. row-level canonical JSON and SHA-256;
3. a sanitized committed authority registry reconciled 55/55 to merged GATE-011E;
4. a non-committed complete package with relationship closure and package SHA-256;
5. strict target classifications and no retargeting;
6. all-or-none import of 55 green plus one dedup authority;
7. separately classified optional derived applications;
8. an append-only `ReviewAuthorityLineageImport` ledger preserving `replicated_at` separately
   from original `reviewed_at` and `created_at`;
9. exact-package idempotency and fail-closed conflicts.

Human decisions are irreducible authority. Continuity applications remain derived evidence.
Acquisition, RAW, Posting, CollectionRun, lifecycle, health and vacancy projection rows are never
imported to manufacture compatibility.

## Exact compatibility result

All 55 green reviewed assessments and observations existed identically in the target. The dedup
run and source algorithm were absent but importable bounded derived dependencies because exact
base observations and historical PIT lifecycle selection already existed. No authority item
required a changed FK or different UUID.

Seventy of 185 green applications were exact-importable; 115 required regeneration. Zero of five
dedup applications were exact-importable. None were retargeted.

## Schema reconciliation

The operational database had a legacy physical `reviewed_by NOT NULL` column not represented by
merged models. C1 removes it only from an empty decision table; otherwise migration fails closed.
The migration independently covers the known legacy names and constraints rather than importing
the suspended GATE-012 migration. Empty `hard_barriers` is declared valid because an empty set of
barriers is already a normal dedup-v0.1 value.

## Engine correction

The dedup engine previously filtered direct prior HUMAN decisions by a stored 011G material
fingerprint. A pre-011G decision has no such field and was invisible even though source material
was reconstructable. The engine now selects the exact unordered pair and causal eligible human
outcomes, reconstructs each source fingerprint, and accepts exactly one material match. Multiple
matches fail closed as conflicting prior human knowledge.

No dedup score, threshold, normalizer, material definition, or human outcome changed.

## Acceptance

On an isolated copy of the operational database, C1 imported 55/55 green decisions, one/one human
dedup decision and two bounded dedup dependencies. A second package execution reused the same
batch with no duplicate authority.

Normal continuity imported 70 exact historical green applications and created 105 target
applications. Seven current assessments remained unmatched: two new-identity assessments and
five material changes. The two original insufficient decisions remain REVIEW. Corrected dedup
continuity reused the exact Brugg/Emmen material and removed it from the critical queue.

At cutoff `2026-08-13T18:18:31.708951Z`, the aligned PIT chain is:

- DedupRun `df796844-4153-4913-b2a9-96b6aa97fbf9`;
- PremiumSegmentRun `932399ea-bd99-444b-a2f6-0bd54149f9ca`;
- DashboardSnapshot `17d36a7c-ebd4-4aa1-a664-576ccf32a870`;
- Day0ReadinessAssessment `41c1c488-e0ee-405d-8d00-19685be21bcb`.

Exact replay returned all four same IDs/fingerprints with one artifact per fingerprint.
Day-0 remains blocked: 19 acquisition-eligible of 29 required, 51 active GREEN, three critical
green reviews, zero critical dedup reviews, and null headline.

## Consequences

Institutional human knowledge can be replicated only with exact identity, reviewed evidence,
foreign-key closure, material reconstruction and causal timestamps. Import time is explicit and
does not replace authority time. Any irreducible authority conflict aborts the whole import.

After independent audit and merge, the real database must be backed up, migrated, preflighted and
given the exact audited package before the preserved GATE-012 branch resumes. GATE-012's frozen
operating contract remains unchanged.

## Validation

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
