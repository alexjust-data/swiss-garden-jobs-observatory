# GATE-011G review lineage audit v0.1

Contract-only commit: `3c5824e0183e151bc0437fd968a926d93264609e`  
Contract frozen before counts: **YES**  
GATE-011F cutoff: `2026-08-12T20:34:34.288688Z`  
Readiness assessment: `abdc4afb-8cff-44f3-8b8b-3054df09cccd`

## Summary

| Review family | Critical at 011F | Material matches | Material changes | New identity/pair | Result before reuse |
|---|---:|---:|---:|---:|---|
| Green | 54 | 54 | 0 | 0 | 52 prior resolved decisions; 2 prior insufficient decisions |
| Dedup | 1 | 1 | 0 | 0 | Prior `KEEP_SEPARATE` |

No new human decision was created. Equality was measured only after the material contract had been committed independently.

## Green lineage

All 54 target assessments have the same `source_id`, governed Posting, `source_native_id`, classifier/taxonomy/review versions, normalized TITLE/TEXT/ORGANIZATION surfaces, classifier result, matched evidence, and reason evidence as a previously reviewed assessment.

| Classification | Count | Consequence |
|---|---:|---|
| `PRIOR_DECISION_MATERIAL_MATCH` | 52 | Eligible for inherited application: 37 confirmed green and 15 confirmed not-green |
| `PRIOR_INSUFFICIENT_MATERIAL_MATCH` | 2 | Eligible application preserves `REVIEW`; uncertainty is not resolved |
| `PRIOR_DECISION_MATERIAL_CHANGED` | 0 | No reuse |
| `NEW_POSTING_NO_PRIOR_DECISION` | 0 | No reuse |
| `PRIOR_POSTING_BUT_NO_HUMAN_DECISION` | 0 | No reuse |
| `OTHER` | 0 | No reuse |

The two insufficient cases are:

| Target assessment | Source | Native ID | Prior decision |
|---|---|---|---|
| `11c02180-38bb-4e48-8f51-1707f02b97b3` | `SRC-OFF-CANTON-AR` | `3996438` | `6d40da88-f664-4e51-ba5f-9b2413426e6c` |
| `4b94a4f8-fceb-47a9-a678-a7729b70b2aa` | `SRC-OFF-CANTON-SG` | `6251` | `60cf7b46-ab36-410a-becb-c1b4af88d15a` |

The 52 resolved matches reconcile to 37 `CONFIRMED_GREEN` and 15 `CONFIRMED_NOT_GREEN`. The sixteenth GATE-011E not-green decision is not in the 011F critical active canonical cohort and therefore has no target application at this cutoff.

## Dedup lineage

Target review `5b2fe52e-93f3-457d-b2aa-36914490e656` is the same governed Posting pair as prior human decision `74550a24-4075-469c-946a-4ea48c045877`:

- Posting `2f4627cf-e9b0-44bc-b56a-dc7aad53180c`, native ID `10139013`;
- Posting `be365ac3-bd94-4363-b945-c56c1e88cbf4`, native ID `10129828`.

Both comparisons retain score `0.7940`, identical feature scores, weights, no hard keys, no hard barriers, identical normalized identity surfaces, distinct stable native IDs and canonical URLs, and active episode 1 on both sides. The later evidence adds only routine `STILL_ACTIVE` observations. Under `dedup-review-material-v0.1`, this is `PRIOR_DECISION_MATERIAL_MATCH`; the prior `KEEP_SEPARATE` decision may be applied without creating a new human decision.

## Scientific conclusion

At this cutoff the operational review reset is entirely explained by immutable observation UUID churn rather than decision-relevant evidence change. Governed reuse should restore 37 green confirmations, 15 not-green confirmations, preserve two unresolved green reviews, and apply one prior dedup separation. These are acceptance expectations derived from material equality, not target counts used to define the contract.

## Second-refresh operational acceptance

Final cutoff: `2026-08-13T06:34:17.993915Z`. The selected refresh window contains exactly one completed run for each of the 20 implemented required Sources: 20 succeeded, 20 healthy, 20 snapshot-complete, 20 counter-consistent, and 20 fresh. No blocked Source was requested. The cohort contains 2,002 new observations.

All 54 new green `REVIEW` assessments have an exact prior material match under `green-review-material-v0.1`: 37 inherit `CONFIRMED_GREEN`, 15 inherit `CONFIRMED_NOT_GREEN`, and two inherit `INSUFFICIENT_EVIDENCE` while correctly remaining `REVIEW`. There are zero material changes, zero new governed Posting identities in this review cohort, zero other unresolved lineage cases, and zero new human decisions.

The two unresolved items remain active, eligible, and authorization-critical:

| Source / native ID | Prior decision | New assessment | Material fingerprint | Raw provenance | Final state |
|---|---|---|---|---|---|
| `SRC-OFF-CANTON-AR` / `3996438` | `6d40da88-f664-4e51-ba5f-9b2413426e6c` | `5f301f43-234e-4149-ac9a-01e82e6e8c2b` | `33c2f1be5a9d36763ecdc70ea95fa160de79a121f6782e392c23a8fa82b79dd0` | byte-identical RAW | `REVIEW`, critical |
| `SRC-OFF-CANTON-SG` / `6251` | `60cf7b46-ab36-410a-becb-c1b4af88d15a` | `d7dc8af8-4160-47ef-b321-eca56defd994` | `b2bb6addca87e3c1ec39a7a6ec9eebe449f26a3eaab395557b37175508c6a0a0` | RAW changed (`c19b...` to `476659...`), material equal | `REVIEW`, critical |

The second-refresh dedup run produced 103 algorithmic review candidates. One is the same governed pair and exact material fingerprint as the prior `KEEP_SEPARATE` decision, so application `6966f84a-325b-4eed-b0c7-5329a5f232f3` inherits it. The other 102 pairs have no prior human decision; they remain noncritical review items. There are zero reused `MERGE` decisions, zero material invalidations, and zero critical dedup reviews.

The inherited pair is native IDs `10139013` / `10129828`, target decision `d5a40701-9fc5-4328-a04a-f347d900025d`, source decision `74550a24-4075-469c-946a-4ea48c045877`, fingerprint `c9f0c0f6a4c0d57062bd15b8024dd434bee2d889a531b74d950277e77d518087`. Routine `STILL_ACTIVE` evidence did not alter episode or economic identity.

## Cross-refresh result

| Metric | GATE-011F | GATE-011G final |
|---|---:|---:|
| Active observations / selected observations | 2,002 | 2,002 |
| Green `REVIEW` assessments before continuity | 54 | 54 |
| Material matches | 54 | 54 |
| Inherited green confirmations | 37 | 37 |
| Inherited not-green decisions | 15 | 15 |
| Inherited insufficient decisions | 2 | 2 |
| Material invalidations | 0 | 0 |
| Critical green reviews after continuity | 54 | 2 |
| Dedup algorithm reviews | 1 | 103 |
| Critical dedup reviews after continuity | 1 | 0 |
| Eligible active green vacancies | 14 | 51 |
| Eligible Sources | 20 | 20 |
| Day-0 | Not authorized | `DAY_0_BLOCKED_BY_DATA_QUALITY` |

The increase from one to 103 algorithmic dedup reviews is disclosed rather than suppressed: 102 are new pairs without human lineage, but none is capable of changing the 51-vacancy public green count at this cutoff and therefore none is authorization-critical.

## Independent-audit correction

Prior audited head: `eb3476b2d5174a279877f7d46302395cb66888f2`.

The audit found that the draft legacy dedup bridge accepted a missing source material fingerprint and that authority/application validation was not fully fail-closed. The correction leaves the frozen contract byte-identical and now reconstructs the source algorithm decision from immutable `algorithm_decision_id`, its DedupRun cutoff and its two historical PostingEvidence inputs. Application persistence and engine consumption independently validate HUMAN method, supported outcome, pair, versions, causality, provenance and source/target/stored material equality. Direct and inherited authority are mutually exclusive. Green applications now validate their immutable evidence, reconcile identical unique collisions and reject multiple matching historical decisions.

For human decision `74550a24-4075-469c-946a-4ea48c045877`, source algorithm `bb37c095-9591-4920-84b7-2d0b69b3e98b` in run `0f241f99-b1da-4c99-8d44-5d5d992e9f88` at `2026-08-12T10:20:02.339073Z` independently reconstructs `c9f0c0f6a4c0d57062bd15b8024dd434bee2d889a531b74d950277e77d518087`. Corrected target algorithm `14ccda11-6fc5-4c28-8dfd-497bf15c8732` in run `d5a44c47-e495-4a0b-b419-824fbba94606` at `2026-08-13T07:52:00Z` reconstructs the same fingerprint. The bridge therefore remains valid by proof, not by same-pair fallback.

The recomputed lineage remains 37 confirmed-green, 15 confirmed-not-green and two insufficient-as-review; dedup remains one inherited `KEEP_SEPARATE`, 102 new noncritical pairs, zero critical dedup reviews and zero reused `MERGE` decisions.
