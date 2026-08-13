# GATE-011G-C1 Review Authority Lineage Contract v0.1

Status: `FROZEN_FOR_IMPLEMENTATION`  
Lineage version: `review-authority-lineage-v0.1`  
Gate: `GATE-011G-C1`

## 1. Scope and invariant

This contract governs deterministic reconciliation of previously accepted human-review authority
between independently persisted PostgreSQL evidence stores. It does not change green relevance,
human-review, material-fingerprint, deduplication, Premium, Day-0, lifecycle, geography, privacy,
source-disposition, or Job-Room semantics.

The invariant is:

```text
merged governance
+ coherent read-only source snapshot
+ exact immutable reviewed-evidence identity
+ exact causal human-decision identity
-> portable human authority

derived continuity evidence
-> exact import only with complete identical dependency closure
-> otherwise regenerate against later target evidence

any identity, evidence, material, or authority conflict
-> fail closed before importing any human authority
```

Database names are locators, never authority. Merged Git governance and exact reconciled evidence
determine which rows may enter an authority package.

## 2. Frozen governance baseline

The package must bind these merged governance decisions:

- GATE-011E merge `cbf1054b329843ea3fff7eeac77ea9342df60147`;
- GATE-011G merge `3f8e5cacc191309188e142ebf28ae0d1115e95e7`;
- C1 baseline `520b68d989d36abfc382143458b30d1f3bad96b2`;
- `green-review-v0.1`;
- `green-review-material-v0.1`;
- `dedup-v0.1`;
- `dedup-review-material-v0.1`.

The expected authority set is a predeclared audit assertion, not import logic: merged GATE-011E
records 55 green human decisions (37 `CONFIRMED_GREEN`, 16 `CONFIRMED_NOT_GREEN`, and 2
`INSUFFICIENT_EVIDENCE`) and one governed human dedup `KEEP_SEPARATE` decision. Export and import
must derive rows from reconciled evidence and must fail if this assertion is not reproduced exactly.

## 3. Evidence classes

### 3.1 Irreducible human authority

Irreducible authority consists only of:

- `GreenRelevanceReviewDecision` under `green-review-v0.1`;
- governed `DedupDecision` rows whose method is `HUMAN`.

For each human decision, primary key, foreign keys, outcome, reason/evidence, governance version,
reviewed time, created time, and immutable reviewed-evidence identity are part of its historical
truth. Import never changes them and never creates a replacement judgment.

### 3.2 Derived continuity evidence

`GreenRelevanceReviewDecisionApplication` and `DedupReviewDecisionApplication` are deterministic
applications of human knowledge. They are not human decisions. A historical application may be
imported only with its original primary key and completely identical FK closure. When its target
does not exist identically, the historical row remains in the source package and current target
continuity may create a new application against current evidence. Historical applications are
never retargeted.

### 3.3 Import provenance

An append-only lineage-import batch records replication provenance. It grants no human authority of
its own and must not replace the original human decision's causal timestamps.

## 4. Source snapshot semantics

Export and audit use one coherent source snapshot under PostgreSQL `REPEATABLE READ, READ ONLY` or
an isolated, demonstrably read-only snapshot with equivalent semantics. The source must not be
migrated, repaired, or written during export.

The source snapshot fingerprint binds, in canonical order:

- server/database identity represented without credentials or DSN secrets;
- transaction snapshot identifier where available;
- schema/migration inventory;
- export start time and bounded source metadata;
- canonical hashes of every included row and relationship;
- merged-governance SHAs.

Aggregate counts are diagnostics only. They do not establish authority.

## 5. Canonical package

The portable `review-authority-lineage-v0.1` package contains:

1. a manifest with versions, governance SHAs, snapshot fingerprint and supported model list;
2. an authority registry containing bounded reconciled identity/provenance metadata;
3. canonical irreducible human-authority rows;
4. the minimum allowed derived dependencies needed to preserve exact FK identity;
5. historical continuity applications in a distinct optional section;
6. an explicit relationship graph;
7. per-row SHA-256 values and one package SHA-256.

Canonical JSON uses UTF-8, sorted object keys, compact separators, arrays sorted by declared stable
identity, RFC 3339 UTC timestamps with microseconds normalized deterministically, UUIDs in canonical
lower-case form, decimal values as exact strings, and lower-case hexadecimal SHA-256 values. The
package hash excludes no semantic field and is computed over the canonical package payload without
its own hash field.

Unsupported models, secrets, DSNs, credentials, unrestricted job descriptions, contact details,
private addresses, or unrelated operational payloads invalidate the package.

## 6. Authority registry

The committed sanitized registry is an audit artifact. It may include authority type, exact UUID,
governance version, outcome, reviewed source assessment/algorithm identity, bounded Source/native
Posting identity, material fingerprint where governed, `reviewed_at`, `created_at`, and canonical
row hash. It must not include unnecessary personal or private evidence.

The registry becomes acceptable only after item-level reconciliation to merged GATE-011E evidence.
Editing the registry is not a substitute for changing or re-adjudicating a human decision.

## 7. Target compatibility classification

Every package row and required relationship receives exactly one preflight classification:

- `PRESENT_IDENTICAL`;
- `ABSENT_IMPORTABLE`;
- `ID_CONFLICT`;
- `UNIQUE_KEY_CONFLICT`;
- `DEPENDENCY_MISSING`;
- `NATURAL_IDENTITY_DIFFERENT_ID`;
- `PRESENT_CONFLICTING`.

`PRESENT_IDENTICAL` is reused. `ABSENT_IMPORTABLE` is insertable only for an explicitly allowed
model with complete identical dependencies. Every other classification aborts the human-authority
transaction. There is no automatic conflict repair, remapping, or subset selection.

## 8. Identity-preservation requirements

### 8.1 Green authority

A green human decision is transplantable only when its referenced
`GreenRelevanceAssessment` is `PRESENT_IDENTICAL` or `ABSENT_IMPORTABLE` under the bounded-derived
rule, and that assessment's exact `PostingObservation` is already `PRESENT_IDENTICAL` in the target.
The decision preserves its assessment FK. Material equality with a different assessment UUID is not
an exact transplant.

### 8.2 Dedup authority

A human dedup decision preserves its decision UUID, DedupRun FK, Posting pair, Observation pair,
algorithm-decision provenance, score/evidence, outcome, `created_at`, and every identity-relevant
field. Source and target must independently reconstruct the same `dedup-review-material-v0.1`
fingerprint. Same pair, same title, or same natural identity alone is insufficient.

## 9. Dependency import policy

Operational base evidence must not be imported merely to make authority fit. Forbidden dependency
imports include:

- `Source`;
- `Posting`;
- `CollectionRun`;
- `PostingObservation`;
- `PostingLifecycleEvent`;
- `RawArtifact`;
- Vacancy membership/projection state;
- Source health evidence.

A missing derived row such as `GreenRelevanceAssessment`, `DedupRun`, or algorithmic
`DedupDecision` may be imported only if this contract's implementation predeclares that model as
allowed and proves that every operational base FK already exists identically, every primary key and
field is preserved, timestamps/fingerprints are preserved, and insertion cannot change acquisition,
lifecycle, source-health, or current-market truth. Uncertainty is a hard stop.

## 10. Transaction and collision rules

The complete irreducible authority set is preflighted before mutation. Import is one atomic
transaction:

```text
55 / 55 exact green authority
+ 1 / 1 exact governed dedup authority
-> commit

any authority conflict or missing forbidden dependency
-> rollback everything
-> import 0 human authority rows
```

Derived applications are handled only after the authority transaction and may be imported in a
separate atomic phase. An exact primary-key row with different canonical content, any different row
under a protected unique identity, or any natural-identity/different-UUID collision fails closed.

## 11. Idempotence

Reapplying the same verified package to the same compatible target:

- creates no duplicate human decision or dependency;
- reuses every identical imported row;
- creates no duplicate historical application;
- reuses the same lineage-import batch identity;
- returns the same package and import fingerprints.

A different package under the same lineage version is rejected unless a future separately governed
lineage version explicitly permits it.

## 12. Causality and replication time

Original `reviewed_at` and `created_at` remain the causal availability times of human knowledge in
the authoritative historical system. Import preserves both. The lineage batch separately records
`replicated_at`, which must not precede package verification or target insertion.

A newly generated target continuity application is available only from its own target `created_at`.
It cannot affect an earlier cutoff merely because its source human decision predates replication.
No import rewrites historical downstream artifacts or operational cycles.

## 13. Post-import continuity

After exact authority import, existing frozen 011G services alone decide current reuse:

```text
same governed identity
+ same exact material fingerprint
+ compatible versions
+ causally available imported human decision
-> new/reused target continuity application

material or identity change
-> no reuse
```

`INSUFFICIENT_EVIDENCE` remains `REVIEW` when reused. No desired count is an acceptance target;
unmatched current assessments may be legitimate new or changed uncertainty.

## 14. Historical operational preservation

The suspended GATE-012 cycle `be7062f8-f587-4e96-aef2-bc4caa1142e2` and all its CollectionRuns,
cutoff, artifacts, status, quality state, and review counts are immutable evidence of what the
operational database knew at execution time. C1 does not inject authority into it, rebuild it, or
reinterpret it.

The real operational database is not modified before independent audit and merge. Development and
acceptance use an isolated copy. C1 performs no Source HTTP request and no human adjudication.

## 15. Schema rule

Schema compatibility is audited independently from the suspended GATE-012 migration. C1 introduces
only the minimum canonical mainline schema required for exact authority representation and the
append-only import ledger. It does not copy an unmerged migration by filename or assumption.

## 16. STOP conditions

C1 stops before importing any human authority when any of the following holds:

- the governed 55/1 authority set is not reproduced exactly;
- merged documentation and source rows disagree on ID, outcome, evidence, or timestamps;
- any original reviewed assessment/algorithm identity cannot be preserved;
- a required operational base row is absent or has another UUID/content;
- a human decision FK would need retargeting;
- dedup source material cannot be independently reconstructed;
- a target collision is not `PRESENT_IDENTICAL`;
- source snapshot coherence or package integrity cannot be proven;
- an unsupported/private/secret-bearing payload enters the package;
- import would alter historical acquisition, lifecycle, source health, PIT artifacts, or cycles.

The terminal report is `EXACT_AUTHORITY_TRANSPLANT_NOT_POSSIBLE` with the complete compatibility
matrix. Designing cross-database external authority attestation is outside C1 and requires a new
predeclared gate.

## 17. Acceptance boundary

C1 closes only when an isolated copy of the operational database proves exact all-or-none human
authority import, separate derived-application treatment, idempotent replay, causal target
continuity, aligned corrected PIT reconstruction, historical-cycle immutability, and zero changes to
frozen scientific semantics. Until merge and a separately controlled real-database procedure,
GATE-012 remains suspended.
