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
