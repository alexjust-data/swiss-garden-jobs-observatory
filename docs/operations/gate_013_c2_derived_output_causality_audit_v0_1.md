# GATE-013-C2 — Derived-output causality audit v0.1

## Scope and frozen evidence

- baseline: `d1243436915dfde055a7482898509d2a55bb727d`;
- contract-only commit: `00c67844287b36bc9a7be0cde0004d5359697b49`;
- contract: `docs/operations/gate_013_c2_derived_output_causality_contract_v0_1.md`;
- real Source HTTP during C2 implementation: `0`;
- real provider HTTP during C2 implementation: `0`;
- real operational database mutations during C2 implementation: `0`.

The real geospatial-v0.2 H2 acceptance completed before C2 and remains immutable evidence:

```text
selected       51
RESOLVED       13
REVIEW         18
UNRESOLVED     20
first provider requests 22
exact retry provider requests 0
historical rows modified/deleted 0
evidence SHA-256 394d84a5bd724911416718eb838a67a0224279fce87b6a86a80139d1cc9bbc16
```

## Incident reconstruction

The manual post-H2 PIT construction exposed a non-convergent contract interpretation. A first
provisional Dedup run created a run-specific continuity application after its `as_of`. Moving the
cutoff beyond that application and rebuilding Dedup created a different target algorithm decision
and another run-specific application after the new cutoff.

Preserved provisional evidence includes:

```text
Dedup 95674989-4187-45e6-9de2-3547cfeef2aa
Premium 4e5e6f99-9a8a-485c-8ef6-15b0306b062b
application 2b34dc9f-3373-40af-9c29-ca38e0dc6d7b

Dedup b0dd39a4-78e4-402b-9851-8fd21464a70e
Premium 001cb8a7-edcf-4e3f-8da2-d74b191f6a0e
application bc1bbc45-4add-4634-acfd-dac5a20519a1
```

No DashboardSnapshot, Day0ReadinessAssessment, completed ObservatoryCycle, Source collection, or
provider request was created from that incomplete chain.

## Root cause

`DedupReviewDecisionApplication` is one-to-one with a target algorithm decision. Every new
DedupRun necessarily creates a new target algorithm decision for a materially identical governed
pair and therefore creates a new application. Treating the application creation time as an input
that the same run must predate makes convergence impossible.

The source human decision and all selected target material are the scientific inputs. The target
algorithm decision and application are derived outputs/provenance materialized by the run.

## Correction

- new cycle identity: `daily-observatory-cycle-v0.4`;
- new cutoff policy: `causal-inputs-and-derived-outputs-aligned-pit-v0.3`;
- v0.1/v0.2/v0.3 completed replay remains explicitly recognized;
- replay validation now binds the historically correct cutoff policy as well as geospatial
  authority;
- initial Dedup no longer advances solely because it created a run-scoped application;
- a geospatial evidence advance still rebuilds aligned Dedup and Premium exactly once;
- run-scoped applications are independently validated against the frozen material contract;
- source human authority must be available by the run cutoff;
- a genuine second geospatial evidence advance remains fail-closed.

No application is backdated, retargeted, changed, or deleted.

## Isolated production-copy acceptance

The source database was read through one coherent PostgreSQL dump and restored as
`swiss_garden_jobs_gate013c2_acceptance`. Its mutable RAW store was a distinct copy containing
10,939 files and 548,636,660 bytes. The operational database and operational RAW root were not
mutated.

The v0.4 cycle reused stored FULL_SOURCE CollectionRuns through a bounded no-HTTP collector:

```text
cycle       3e1ffc62-3b2d-49c4-a19b-df99acd01d75
status      SUCCEEDED_NOT_AUTHORIZED
cutoff      2026-08-26T14:14:40.522349Z

Dedup       c07726ec-5c5a-4da3-ac0d-f5d2545f78cd
fingerprint ad290a1b73247a4363e66a506fa11547e9623d9b38b7f1b78cd99a99715c2a58

Premium     d2b253c1-74e4-4709-940c-0eb0b111cf90
fingerprint 5606baaa7281905f114323f34c96453118c949122db0c491bd6fdf0766eb0c07

Dashboard   db178e9a-3444-42ba-ac83-e6dba716db36
fingerprint 8c14717a93b6b6f062d36fa8598fc4941ba52479c6e8dc312eea99a50545b377

Readiness   b3ae08e9-6308-4129-811a-c873b8fb1ad2
fingerprint 79b4eb443fc944119184dc801308b6c70a8f532b6378010196de5a49193e3ca0
```

The exact run-scoped application was:

```text
application             164ccaeb-de1b-4f83-a854-ab80539901a2
created_at              2026-08-26T14:15:53.432885Z
created after cutoff    YES
source human decision   74550a24-4075-469c-946a-4ea48c045877
source created_at       2026-08-12T15:43:26.564611Z
source causal           YES
material fingerprint    c9f0c0f6a4c0d57062bd15b8024dd434bee2d889a531b74d950277e77d518087
```

Geospatial replay selected/reused all 51 v0.2 identities, made zero provider requests, and yielded
13 mappable plus 38 public-unmapped records. The exact cycle retry returned the same four artifact
IDs and performed zero collector or provider activity. Day-0 remained `DAY_0_NOT_READY`; C2 did not
authorize or change policy.

## Mechanical validation

```text
GATE-013/C2 focused                         21 passed
GATE-012 audit correction                  38 passed
GATE-012 base                              18 passed
Dedup PIT/review continuity                21 passed
GATE-014 scheduler                         28 passed
full pytest                                667 passed, 2 skipped
Playwright dashboard                        4 passed
Ruff                                       PASS
mypy                                       PASS — 178 source files
Django check                               PASS
migration drift                            NONE
isolated PostgreSQL copy                   PASS
isolated v0.4 causal cycle                 PASS
exact cycle retry                          PASS
Source HTTP                                   0
provider HTTP                                 0
real operational database mutations          0
```

CI, GitGuardian, and review-thread evidence are recorded after pushing the exact PR head.

