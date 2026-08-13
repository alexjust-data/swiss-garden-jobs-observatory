# GATE-011D-C2 Policy Artifact Identity Reconciliation Contract v0.1

Status: FROZEN BEFORE IMPLEMENTATION AND DATABASE LINEAGE MEASUREMENT

## Purpose

This contract reconciles immutable Day-0 authorization-policy artifacts that share one semantic
policy version but were produced by different pre-merge and merged representations. It changes no
coverage, freshness, authorization, source, review, Dedup, Premium, geography, or Job-Room
semantics.

The semantic policy remains `day0-authorization-v0.1`. Its accepted merged definition is governed
by the final merged GATE-011D Git evidence and ADR 0015:

- denominator: 29 required Sources;
- minimum passing count: 24 and coverage at least 0.80 with equal Source weighting;
- Federal minimum: 1 of 1;
- City minimum: 4 of 6;
- derived Canton floor: 17 of 22;
- freshness: accepted healthy, complete FULL_SOURCE evidence at
  `CollectionRun.finished_at`, no older than 72 hours at the inclusive wall-clock boundary;
- all 29 required Sources retain their governed dispositions.

## Immutable history

Existing `Day0AuthorizationPolicy`, `Day0ReadinessAssessment`, and `Day0SourceUniverse` rows are
historical evidence. This gate never edits or deletes them, changes their foreign keys, relabels a
legacy artifact, or pretends a pre-merge artifact never existed.

Merged Git governance determines the canonical accepted policy definition. A draft or pre-merge
artifact remains queryable historical evidence but does not acquire canonical authority merely by
having been persisted first.

## Identity boundary

A semantic policy version names governed scientific meaning. A policy artifact is one immutable
materialization of that meaning claim and is identified by its exact input fingerprint. These are
distinct identities.

Multiple immutable artifacts may share a semantic policy version when historical development
evidence already exists. An identical fingerprint is always reused and never duplicated.

The artifact table therefore does not encode authority through uniqueness of `policy_version`.
`input_fingerprint` remains unique, and `policy_version` remains indexed for discovery.

## Explicit authority

Authority is append-only evidence represented by
`Day0AuthorizationPolicyDesignation`.

The designation pins at least:

- `designation_version = day0-authorization-policy-designation-v0.1`;
- semantic `policy_version`;
- the exact authoritative policy artifact;
- `authority_basis = MERGED_GOVERNANCE_DECISION`;
- bounded governance evidence identifying PR #19, its merged SHA, final policy commit, and ADR 0015;
- an effective time, creation time, and exact input fingerprint.

For one designation version and semantic policy version, exactly one artifact is authoritative.
An identical designation is idempotently reused. A conflicting designation fails closed. A future
scientific policy change requires a new semantic policy version; current Python output cannot
silently replace the designation.

## Canonical selection

`ensure_authorization_policy()` deterministically constructs the final merged v0.1 configuration
from frozen repository policy constants, calculates its canonical fingerprint, ensures or reuses
that exact immutable artifact, ensures or reuses the matching authority designation, validates the
designation and governance evidence, and returns the designated artifact.

A different non-authoritative artifact under the same semantic version is preserved and does not
block canonical selection. A conflicting designation, malformed governance evidence, or unexpected
designated artifact fails closed.

## Historical and current replay

Historical readiness assessments remain pinned to their original policy artifact and must replay
unchanged by exact assessment identity. New readiness assessments use the designated canonical
artifact. No historical assessment is reinterpreted using current authority.

`Day0SourceUniverse.policy_version` is audited separately. It may remain a semantic-version pin only
if its meaning and fingerprint do not depend on authorization-artifact representation. If exact
artifact identity is material, the correction must add the smallest append-only pin without
rewriting historical universes.

## Database paths

On a clean database, normal execution creates only the canonical final v0.1 artifact and its
designation. It never manufactures the pre-merge artifact. Repeated execution reuses both.

On an existing database, the legacy artifact and all referencing evidence remain unchanged.
Execution creates or reuses the canonical artifact and designation. New readiness uses canonical
authority.

## Causality and publication

Designations may influence only readiness evidence created after the designation is causally
available. Historical API responses by exact readiness ID remain historical. Current/public
selection may use only the authoritative designation available at its cutoff.

## Failure semantics

The system fails closed for:

- conflicting authority under the same designation version;
- a designation whose semantic version differs from its artifact;
- malformed or incomplete governance evidence;
- a stored designation fingerprint that does not match its immutable contents;
- current-code drift that produces an undesignated artifact;
- attempted mutation or deletion of policy artifacts or designations.

## Explicit exclusions

This gate does not create `day0-authorization-v0.2`, change the final merged v0.1 policy, run Source
HTTP requests, collect observations, adjudicate reviews, resume GATE-012, import its migrations, or
modify its frozen operating contract.
