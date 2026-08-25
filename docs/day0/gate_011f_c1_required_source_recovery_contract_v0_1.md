# GATE-011F-C1 — Required-source recovery contract v0.1

Status: `FROZEN_FOR_RECONNAISSANCE_AND_IMPLEMENTATION`

- Baseline: merged GATE-010-C4 `99e39312535f33554a973110cba196c253628945`
- Prior recovery governance: GATE-011F / `gate_011f_source_recovery_contract_v0_1.md`
- Required-source universe: 29 Sources
- Current implemented ceiling: 20/29
- Day-0 minimum: 24/29

## 1. Purpose

This correction re-evaluates the nine required Sources that remain
`ACCEPTED_BLOCKED` using new, bounded official evidence. It may implement a
Source only when that Source independently satisfies every already-frozen
GATE-011F transition requirement.

The gate does not target four favorable outcomes. Zero, one, or several Sources
may be recovered. Evidence decides each result independently.

## 2. Scientific and historical invariants

This gate changes none of the following:

- the 29-Source required universe;
- the 24/29 coverage minimum;
- `day0-coverage-v0.1`;
- `full-source-freshness-v0.1`;
- `day0-authorization-v0.1`;
- Posting, Vacancy, lifecycle, green, dedup, Premium, geography or privacy
  semantics;
- historical C-6 or GATE-011F dispositions;
- historical CollectionRuns, readiness assessments or operational cycles.

A new disposition is append-only evidence. A historical blocked decision is
never edited or deleted.

## 3. Candidate set and outcomes

The exact candidate set is:

`AI`, `AG`, `BE`, `FR`, `JU`, `NW`, `OW`, `UR`, and `VS`.

Each Source receives exactly one current C1 outcome:

- `RECOVERED_IMPLEMENTED`;
- `STILL_BLOCKED_SAME_REASON`;
- `STILL_BLOCKED_NEW_EVIDENCE`;
- `BLOCKER_CLASS_CHANGED`; or
- `SOURCE_CONTRACT_DRIFT`.

Prioritization for investigation is not implementation authority.

## 4. Common recovery requirements

`RECOVERED_IMPLEMENTED` requires all of the following:

1. the canonical canton-employer Source and every mandatory vacancy surface
   are enumerated;
2. official ownership and the applicable robots/access contract are proven;
3. every current economic opportunity has a stable source-native identity or
   an already-authorized canonical-URL fallback;
4. pagination, explicit zero state and complete exhaustion are deterministic;
5. same-employer surfaces, separate employers, duplicate language
   presentations and non-vacancy material are explicitly classified;
6. failure of any mandatory surface fails the whole `FULL_SOURCE` run;
7. immutable RAW, PostingObservation, health and completeness counters can be
   produced by the existing governed pipeline; and
8. two consecutive real `FULL_SOURCE` acceptance runs are `SUCCEEDED`,
   `HEALTHY`, complete, counter-consistent and exactly replayable.

One working ordinary listing never compensates for an unresolved mandatory
teaching, training, magistracy, police or gazette surface.

## 5. Access and reconnaissance

Reconnaissance uses only bounded public official evidence. Before requesting a
candidate vacancy origin, record its official linkage and applicable robots
decision. Never request a prohibited path.

Forbidden:

- authentication or session reuse;
- private tokens;
- alternate user-agent evasion;
- browser automation used to bypass access controls;
- mirrors, aggregators or Job-Room as a substitute for canonical employer
  exhaustion;
- fuzzy identity, fabricated IDs or inferred empty states.

Search-engine discovery may locate an official page but is never itself proof
of completeness, identity or current zero state.

## 6. Source-specific unchanged conditions

- AI: vacancy-level apprenticeship identity plus a complete authorized ordinary
  contract.
- AG: independently official, complete and robots-permitted origin.
- BE: authorized and exhaustible KSML/STEZE surfaces, or governed proof that
  they are outside the canonical Source.
- FR: completed migration or authoritative cross-platform identity and
  exhaustion.
- JU: explicit teaching list/zero contract and item-level resolution of the
  `Autres` employer boundary.
- NW: `NW-1616` proven one standing opportunity or native identities separating
  simultaneous cohorts/routes.
- OW: authorized complete alternate origin or applicable platform/access
  change.
- UR: reproducible listing and mandatory-detail delivery through two
  consecutive governed full runs.
- VS: deterministic ownership, bilingual identity and exhaustion across every
  mandatory surface.

## 7. Implementation boundary

No adapter, endpoint or reference-data disposition changes until the complete
read-only compatibility matrix for that Source is documented.

A recovered Source is implemented in the smallest repository-consistent
adapter. It must preserve source-native identity, fail closed on incomplete
surfaces, and use no new scientific interpretation.

Sources that remain blocked receive documentation only. They receive no
synthetic CollectionRun and do not become implemented merely to close the
numeric coverage gap.

## 8. Acceptance and causality

Acceptance for each implemented Source requires:

- isolated PostgreSQL development first;
- governed RAW evidence in a distinct non-operational root;
- two consecutive complete live runs under the bounded HTTP policy;
- exact replay with no hidden manual correction;
- stable native identities across the two runs, while allowing legitimate live
  content change;
- reference import idempotence;
- no mutation of historical blocked evidence;
- regression validation for lifecycle, dedup, Premium, Dashboard and Day-0.

The real operational database and canonical RAW root remain unchanged before
independent audit and merge.

## 9. STOP conditions

Stop the affected Source without implementing it if any of these occurs:

- access legality is unclear or a required path is prohibited;
- a mandatory surface cannot be enumerated or exhausted;
- identity would require a fabricated or fuzzy key;
- employer ownership cannot be reconciled;
- a zero state is inferred rather than explicit;
- either consecutive full run is incomplete, degraded or manually repaired;
- production evidence contradicts the repository contract;
- a frozen scientific contract would need to change.

Stopping one Source does not stop safe work on other candidates.

## 10. Delivery

The gate must publish a complete nine-Source audit matrix with bounded official
evidence, access result, identity result, exhaustion result, outcome and exact
implementation authorization. Any code change must include focused tests and a
draft PR. Do not merge without independent semantic audit.
