# Decision 0020: GATE-011D-C2 Day-0 policy artifact identity

## Status

Accepted for implementation; pending independent audit and merge.

## Baseline and predeclaration

- merged GATE-011G baseline: `3f8e5cacc191309188e142ebf28ae0d1115e95e7`;
- frozen correction contract: `docs/day0/gate_011d_c2_policy_identity_reconciliation_contract_v0_1.md`;
- contract-only commit: `e671260ab2fbdda9a9b8385f1ab3502156f9badc`.

GATE-012 remains suspended at branch `gate-012-daily-observatory-operations`, head
`7e6fe9d698424c306029ce636c4d36ffe81d4e01`. Its operating-contract commit
`f2b77eeb5e8514d6a972c3ae95d85b12aab3b22e` was not imported or changed.

## Root cause

PR #19 persisted an immutable `day0-authorization-v0.1` artifact from development commit
`2c07f634…`. Before merge, `75cab6b54…` finalized the same semantic version with the governed
17-Canton derived floor and corrected freshness descriptor. The final tree `76c427ef…` was squash
merged as `1a1af1f5…`. The original schema incorrectly assumed that one semantic version could
have only one immutable artifact, so the legitimate historical row collided with merged truth.

The pre-merge fingerprint reconstructs exactly as `ce0e3c…4230`; the final merged artifact is
`a72dd5…294e`. This is not `day0-authorization-v0.2`: no scientific decision changed after merge.

## Decision

`Day0AuthorizationPolicy` remains append-only and uses unique `input_fingerprint` as artifact
identity. `policy_version` becomes a non-unique indexed semantic label.

New append-only `Day0AuthorizationPolicyDesignation` explicitly assigns authority. For
`day0-authorization-policy-designation-v0.1` and one semantic policy version, exactly one exact
artifact may be authoritative. It pins the artifact, merged-governance basis, PR #19, merge SHA,
final policy/tree commits, ADR 0015, effective time and its own deterministic fingerprint.

`ensure_authorization_policy()` reconstructs the merged configuration, verifies the expected
canonical fingerprint `a72d…294e`, ensures/reuses that exact artifact, and validates/ensures the
designation. A legacy artifact is preserved. A conflicting designation, malformed evidence,
future current-code drift, or authority unavailable at the requested PIT cutoff fails closed.

New v0.1 readiness must use the designated artifact. Exact historical readiness remains pinned to
its original policy FK and is never reinterpreted. `Day0SourceUniverse` safely retains its semantic
version pin because its fingerprint and Source-selection meaning do not depend on exact
authorization-artifact representation; readiness already pins the exact artifact.

## Migration and database behavior

Migration `day0/0003_policy_artifact_authority.py` relaxes the version uniqueness and adds the
designation table and constraints. It performs no data rewrite.

On a clean database, normal execution creates only `a72d…` plus its designation and reuses both.
On an existing database, `ce0e…`, its readiness FKs and APIs remain unchanged; the canonical
artifact and designation are appended. No old evidence is updated or deleted.

## Scientific invariants

The final policy remains:

- coverage `day0-coverage-v0.1`, 24/29 and at least 0.80, equal weighting;
- Federal 1/1, City at least 4/6, derived Canton floor 17/22;
- freshness `full-source-freshness-v0.1`, `CollectionRun.finished_at`, inclusive 72 hours;
- all 29 dispositions governed, including nine blocked Sources in the denominator.

Tests prove 23/29 fails, 24/29 may pass only with structural minima, and no v0.2 is introduced.
Green, review continuity, Dedup, Premium, geography, Job-Room and blocked-source semantics are
unchanged. C2 performs no HTTP collection and no human adjudication.

## Acceptance

Isolated existing and clean PostgreSQL paths both migrate, import reference data twice and pass
replay. The existing-copy historical row/readiness remain exact. A new canonical readiness uses
the designated FK and replays to one ID/fingerprint. Full validation results and final GitHub head
are recorded in the PR handoff rather than made normative here.

## Independent-audit correction

The independent audit of head `dc23196315bf7d3cef8def5a40b3ac92cd9da089` found that
`MERGED_GOVERNANCE_DECISION` used `effective_at=2026-08-12T08:09:55Z`, while GitHub records PR
#19 `merged_at=2026-08-12T08:09:56Z`. Authority cannot precede the merge that grants it.

The correction pins `merged_at=2026-08-12T08:09:56Z` in bounded governance evidence and sets
`effective_at` to that exact instant. Model validation requires the merged timestamp, parses only
the deterministic UTC `Z` representation and requires exact equality. One second before merge
fails closed; the exact merge second is inclusive.

This changes only designation evidence and its fingerprint. The canonical scientific policy
fingerprint remains `a72dd56dee6f6a580e1904c4e5427dd3dab9109775fd83722f2108cafb8d294e`.
Corrected clean and existing-copy acceptance independently produced designation fingerprint
`abe3278ddabb091080f4e65cc6ec9e8d5866cbc5ca6280cc9b4d57d4d2107500`, preserved the legacy
policy/readiness/API exactly, and replayed the canonical readiness deterministically. The frozen
predeclaration contract remains byte-identical.

## Resuming GATE-012

Only after C2 independent audit and merge: synchronize `main`, merge corrected `main` into the
preserved GATE-012 branch, resolve mechanical conflicts, keep its frozen operating contract
unchanged, and resume according to that contract. C2 does not open PR #24.
