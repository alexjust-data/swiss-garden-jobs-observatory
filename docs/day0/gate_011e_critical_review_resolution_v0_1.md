# GATE-011E critical review resolution v0.1

The queue was frozen from readiness assessment `ee972d80-fe6e-47fb-8e62-001e5028abd5`. Decisions use exact PIT title, description, responsibilities, qualifications, structured source payload and classifier matches. No title-only decision was made where source duties were absent. Original classifier assessments remain immutable.

## Result

| Type | Initial critical | Confirmed green | Confirmed not green | Insufficient / unresolved | Other resolution |
|---|---:|---:|---:|---:|---:|
| Green relevance | 55 | 37 | 16 | 2 | 0 |
| Dedup | 1 | n/a | n/a | 0 | 1 KEEP_SEPARATE |

Every green decision is an append-only `GreenRelevanceReviewDecision` under `green-review-v0.1`; its evidence stores the observation, Source, canonical URL, reviewed surfaces and original classifier result. Premium pins both the effective result and exact decision ID, so later decisions cannot leak backward.

### Reason groups

| Outcome | Reason code | Count | Governed basis |
|---|---|---:|---|
| CONFIRMED_GREEN | `GREEN_DUTIES_EXPLICIT` | 37 | Explicit gardening, plant, tree, green-space, nature-site or equivalent maintenance duties |
| CONFIRMED_NOT_GREEN | `DUTIES_OUTSIDE_GREEN_SCOPE` | 16 | Administrative, legal, engineering, road/building, forestry/agricultural or generic facility duties without governed green-market work |
| INSUFFICIENT_EVIDENCE | `SOURCE_DUTIES_INSUFFICIENT` | 2 | Betriebsunterhalt apprenticeship publication lacks duties needed to decide without title-only inference |

The two unresolved IDs are `6a48ceea-da05-4243-b52e-6f3b223d478f` (AR, BBZ Herisau) and `bde39043-5816-42a0-8bbc-186170372bba` (SG, Rorschach). They remain authorization-critical.

Dedup review `8111e37f-2995-421b-be5f-7c3554be2d3f` was kept separate. Source-native IDs `10139013` and `10129828`, distinct canonical URLs, workplaces Brugg/Emmen, publication dates and duty sets prove two economic opportunities despite shared title, employer and HR contact. Human decision: `74550a24-4075-469c-946a-4ea48c045877`.

## PIT checkpoints

Pre-review: 20 eligible Sources, 8 eligible-market green-confirmed vacancies, 55 critical green reviews and one critical dedup review.

Post-review cutoff: `2026-08-12T15:46:59.258290Z`. It contains 20 eligible Sources, 51 eligible-market green-confirmed active Vacancies, two unresolved critical green reviews and zero critical dedup reviews. The increase follows evidence-based confirmations; it is diagnostic only because coverage remains below policy.