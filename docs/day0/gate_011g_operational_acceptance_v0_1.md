# GATE-011G operational acceptance v0.1

Baseline: `0d0acd753b42d004d3243866d4daf7449dafebe8`

Contract-only commit: `3c5824e0183e151bc0437fd968a926d93264609e`

Final cutoff: `2026-08-13T06:34:17.993915Z`

## Controlled second refresh

The window contains only the following 20 implemented required Sources. Every run is `SUCCEEDED`, `HEALTHY`, `snapshot_complete=true`, has equal discovered/fetched/parsed/persisted/classified/lifecycle counters, and is fresh at the final cutoff. Blocked Sources requested: **0**.

| Source | CollectionRun | Count | Finished UTC |
|---|---|---:|---|
| AR | `590ae10c-df5d-4e81-8e58-4c821d5f1b39` | 12 | 2026-08-12 21:39:42 |
| BL | `0c0421de-c3f0-4f79-8546-d4dbc9b922df` | 47 | 2026-08-12 21:41:06 |
| BS | `cde6148a-c4a9-4bd0-ba3f-fe6cbfafe4cb` | 96 | 2026-08-12 21:43:49 |
| GL | `7379a34c-a01d-497e-b1f0-f5d694fd954d` | 21 | 2026-08-12 21:44:19 |
| GR | `a2086257-0c91-4f47-996f-2da95fe9e5d3` | 40 | 2026-08-12 21:45:16 |
| LU | `69e67434-535b-4b96-a346-b87e1aeddcd7` | 75 | 2026-08-12 21:46:59 |
| SG | `686cbc39-b165-4c09-a9e7-6f14dbbf0f8a` | 79 | 2026-08-12 21:49:18 |
| SH | `db5992c1-4325-4751-8d4f-0562cc86dd3c` | 19 | 2026-08-12 21:49:49 |
| SO | `56089ceb-693d-4e4b-a1c9-fa4d5022ad68` | 31 | 2026-08-12 21:50:38 |
| SZ | `dd835804-4002-4bba-b177-4edba822eb65` | 26 | 2026-08-12 21:51:22 |
| TG | `de19e0d5-67f2-4928-96e3-1601ad342835` | 33 | 2026-08-12 21:52:14 |
| ZG | `fd51742b-1a9e-4056-bb88-f66472340ccb` | 26 | 2026-08-12 21:53:04 |
| ZH | `8c79f62a-ab20-489e-8ddb-4eece291b862` | 167 | 2026-08-12 21:57:54 |
| City Bern | `4912c10e-e143-4793-b804-c9b269223b45` | 38 | 2026-08-12 21:59:01 |
| City Luzern | `513425d9-8627-4512-8e6f-f9af7b3c4704` | 21 | 2026-08-12 21:59:34 |
| City Schaffhausen | `916c134c-98c9-4870-ade3-5ed7d5fce77a` | 56 | 2026-08-12 22:01:51 |
| City St. Gallen | `9743dce1-a236-43dc-b7ec-07bdbb1f8402` | 42 | 2026-08-12 22:04:47 |
| City Winterthur | `57bf06aa-5dc4-43ed-8ea4-ce694357227f` | 75 | 2026-08-12 22:06:37 |
| City Zurich | `c902eb73-b6b3-4751-8953-10666b062c30` | 490 | 2026-08-12 22:21:12 |
| Jobs Admin | `eec5874f-c67f-4e0a-be7d-b4c1c7e678c5` | 490 | 2026-08-12 22:36:37 |

Total selected observations: **2,002**.

## Final aligned PIT chain

| Layer | ID | Input fingerprint | Exact replay |
|---|---|---|---|
| DedupRun | `2df4e227-dbbb-477d-a47e-aafdc1567ff3` | `435fae525f1cf0185c6e1687bb067cdfa1350dc58eae1fff8bec1c408fe335f2` | same ID, reused |
| PremiumSegmentRun | `971bb3ab-d300-4525-8862-434346fe2563` | `a5126bad31a856b136a38bedeaeed5acd2c4e6b09a3eda31db58d542f4e33ec7` | same ID, reused |
| DashboardSnapshot | `f9e84544-19b6-4741-bc5e-c0ec167c9ed6` | `5e0ffe8ff550be3376f01cbadc9a6376a2b5f769214e91f437df5e39a4c230b2` | same ID, reused |
| Day0ReadinessAssessment | `5d33f761-5c81-473c-8f35-f806d204f6b0` | `e36dd4e628997ca5e4265f2830ba12fe4118e82f9ce2b26590eaf4abcd49dd72` | same ID, reused |

Dedup and Premium select the same 2,002-observation universe. Dashboard construction passed. Repeating continuity created zero applications and reused 185; repeating every PIT layer returned its original ID and fingerprint. There is one artifact per listed fingerprint.

## Final Day-0 state

Required/implemented/eligible Sources: **29 / 20 / 20**. Structural coverage is Federal **1/1**, Cities **6/6** (minimum 4), and Cantons **13/22** (derived floor 17). The market contains 51 eligible active `GREEN_CONFIRMED` vacancies, two critical green reviews, zero critical dedup reviews, zero other critical reviews, and 102 noncritical dedup reviews.

Authorization is `DAY_0_BLOCKED_BY_DATA_QUALITY`. Failures are acquisition coverage 20/29 below 24/29 and the two critical green reviews; the nine frozen blocked-source dispositions remain denominator-only evidence. The unauthorized headline is `null`.

An earlier provisional derivation used a cutoff before its continuity application became causally available. It is immutable database evidence but is explicitly excluded. The final cutoff above was fixed only after all applications existed, then replayed after the cutoff with no intervening collection evidence.

## Independent-audit corrected PIT chain

After audit of head `eb3476b2d5174a279877f7d46302395cb66888f2`, validation was hardened without changing the frozen contract or collection corpus. At cutoff `2026-08-13T07:52:00Z`, the corrected engine created and then exactly replayed:

| Layer | ID | Fingerprint |
|---|---|---|
| DedupRun | `d5a44c47-e495-4a0b-b419-824fbba94606` | `0ede0abf31d5c064640739eb6d48194c5d4afd837ccc4b58596b5ef413070af8` |
| PremiumSegmentRun | `3c522be5-464d-4b4c-abc4-87bb90bdda33` | `c6e39be1d14adb17b7649da42630b8e31da278048f266a14fab2001f24ebee8c` |
| DashboardSnapshot | `23ae1e19-9dc4-4e58-9e9a-7fa28c0dfcc8` | `3ffcd09e91acb99137cab328cd8ddacf2840977e76e5cb7c66d03989ea3c2e41` |
| Day0ReadinessAssessment | `d0500be7-96a6-450a-8089-26ef0ef8a0ae` | `e9b6cd5bc9e2ed9d86318096d391ebe1928bb2df6a0e944e4fe4dd336d748eb4` |

Every replay returned the same ID/fingerprint and each fingerprint has one artifact. Green continuity created zero duplicates and reused 185 applications. The immutable refresh evidence remained fresh: 20/20 eligible, no blocked Source requested. Final state remains 51 active green vacancies, two critical green reviews, zero critical dedup reviews, Day-0 blocked at 20/29 and headline null.
