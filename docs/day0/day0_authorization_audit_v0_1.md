# Day-0 authorization audit v0.1

## Aligned point-in-time inputs

```text
as_of                  2026-08-12T07:30:00Z
DedupRun               b0ca3818-449a-40ef-9c2c-d75977978c06
fingerprint             917c24777499ce9ba1e00382d2c643d7e9370d0b8ebb2f3531104cf230e1a905
PremiumSegmentRun       5464f4c5-13d1-47b4-a0fb-c3ada61f83ab
fingerprint             b34575cd813f24aff29f2b84584075cfeb4e79eadb051b5e7e50ff3819b29717
DashboardSnapshot       e8fafe8d-ebb0-42e2-9d8a-2acebb47e313
fingerprint             d9cf027490ec22f2d577100ba9c61ad7f86b1388fea0528922159ee6237b0a5f
Day0ReadinessAssessment d078eea3-495b-43b7-bc37-20a199e1a3a2
fingerprint             c350b8f946ea60dde0f11b55102551caadc5004a3c05bbad09ea032a2f3eb362
```

## Required-source evidence

Age is measured from accepted `FULL_SOURCE.finished_at`; `<=72h` is fresh.

| Source | Disposition | Stratum | Selected run | Age h | Complete | Healthy | Freshness | Eligible | Reason |
|---|---|---|---|---:|---|---|---|---|---|
| SRC-OFF-JOBS-ADMIN | IMPLEMENTED | Federal | efc8d5e2-c566-4657-ab5b-689bb3aa3b16 | 31.538 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-AG | BLOCKED | Canton | ? | ? | no | no | BLOCKED | no | POLICY_BLOCKED |
| SRC-OFF-CANTON-AI | BLOCKED | Canton | ? | ? | no | no | BLOCKED | no | SEMANTIC_IDENTITY_BLOCKED |
| SRC-OFF-CANTON-AR | IMPLEMENTED | Canton | 3ff09ba0-5965-444a-b377-edcdb820fe14 | 35.816 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-BE | BLOCKED | Canton | ? | ? | no | no | BLOCKED | no | MULTI_SURFACE_BLOCKED |
| SRC-OFF-CANTON-BL | IMPLEMENTED | Canton | 6f40e61d-635a-4c00-843e-ade99fe2b33e | 33.401 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-BS | IMPLEMENTED | Canton | 402e8088-78d1-4db2-88a6-635989601dd7 | 31.519 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-FR | BLOCKED | Canton | ? | ? | no | no | BLOCKED | no | MULTI_SURFACE_BLOCKED |
| SRC-OFF-CANTON-GL | IMPLEMENTED | Canton | d6635c88-3e21-41e6-a9eb-81a31e186709 | 12.197 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-GR | IMPLEMENTED | Canton | cebbd705-9cc6-4f40-89a7-aa3b274c7d1a | 23.937 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-JU | BLOCKED | Canton | ? | ? | no | no | BLOCKED | no | SOURCE_UNIVERSE_BLOCKED |
| SRC-OFF-CANTON-LU | IMPLEMENTED | Canton | 90cfcdf2-06f0-459e-aebd-e9867f2d335d | 16.456 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-NW | BLOCKED | Canton | ? | ? | no | no | BLOCKED | no | SEMANTIC_IDENTITY_BLOCKED |
| SRC-OFF-CANTON-OW | BLOCKED | Canton | ? | ? | no | no | BLOCKED | no | POLICY_BLOCKED |
| SRC-OFF-CANTON-SG | IMPLEMENTED | Canton | 95bc8a59-3b12-4852-a469-607432eb700b | 21.021 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-SH | IMPLEMENTED | Canton | 47f65919-1f5b-4a4d-b4d7-f5d9d2472d45 | 15.267 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-SO | IMPLEMENTED | Canton | aa7f3fd5-aa9d-4fb1-808b-ebe42f637302 | 23.897 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-SZ | IMPLEMENTED | Canton | 2a18933d-35b2-433d-842d-89375540b901 | 23.880 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-TG | IMPLEMENTED | Canton | 846a4c5c-7b79-4708-afe6-81d13b4de161 | 21.002 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-UR | BLOCKED | Canton | ? | ? | no | no | BLOCKED | no | TECHNICAL_RELIABILITY_BLOCKED |
| SRC-OFF-CANTON-VS | BLOCKED | Canton | ? | ? | no | no | BLOCKED | no | MULTI_SURFACE_BLOCKED |
| SRC-OFF-CANTON-ZG | IMPLEMENTED | Canton | 00f00469-6109-447f-8718-23590f00e5bb | 33.661 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CANTON-ZH | IMPLEMENTED | Canton | 3a9d318a-0afb-4b33-a22d-53599e8cf8af | 35.708 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CITY-BERN | IMPLEMENTED | City | 21c33cc5-6029-4c65-ad0e-77bfbafd9ffb | 38.965 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CITY-LUZERN | IMPLEMENTED | City | db2f919a-dc19-4397-b6bc-5834913ef8d1 | 38.438 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CITY-SCHAFFHAUSEN | IMPLEMENTED | City | c91f686d-0dd1-4eaf-9d41-a7bbdddfc838 | 38.935 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CITY-STGALLEN | IMPLEMENTED | City | 80079285-ade8-498c-8550-f006f62d4051 | 14.973 | yes | yes | FRESH | yes | accepted evidence |
| SRC-OFF-CITY-WINTERTHUR | IMPLEMENTED | City | 49be55a0-8ae7-4b13-8d7c-2b7da74f5df9 | 87.531 | yes | yes | STALE | no | age > 72h |
| SRC-OFF-CITY-ZURICH | IMPLEMENTED | City | 0a5ec4df-a61b-4add-b85a-4f086cc037af | 87.388 | yes | yes | STALE | no | age > 72h |

## Evaluation

```text
governed disposition       29 / 29 PASS
implemented complete       20 / 29
healthy                    20 / 29
fresh eligible             18 / 29 FAIL (minimum 24)
structural federal          1 / 1  PASS
structural city             4 / 6  PASS
derived canton guarantee   17 / 22 when total + federal pass
current canton diagnostic  13 / 22 (total already fails)
blocked                     9
stale                       2
unhealthy                   0
incomplete implemented      0

postings/vacancies          1,867 / 1,867
AUTO_MERGE                  0
cross-source AUTO_MERGE     0
dedup REVIEW               99 (noncritical for eligible Day-0 cohort)
corpus GREEN_CONFIRMED     14
eligible GREEN_CONFIRMED    8
corpus green REVIEW        53
critical green REVIEW      39
excluded noncritical green 14
eligible mappable           0 / 8
```

## Authorization result

`DAY_0_NOT_AUTHORIZED` (stored status: `DAY_0_BLOCKED_BY_DATA_QUALITY`). Failed conditions are acquisition coverage 18/29 < 24/29 and 39 authorization-critical green reviews inside the exact eligible Source cohort. Federal and city structural rules pass. The current 13/22 canton count is diagnostic, not a redundant independent blocker: passing total plus federal with at most six cities would guarantee at least 17/22 cantons.

The public market figure is `null`. The corpus contains 14 public `GREEN_CONFIRMED` records, but only 8 have canonical observations owned by the 18 fresh, healthy, complete required Sources. If this assessment had otherwise authorized publication, the immutable assessment envelope—not the whole DashboardSnapshot—would expose 8.

The eligible Source set is persisted in `metrics.day0_market_state.eligible_source_ids`. Exact DashboardSnapshot responses remain independent of later readiness assessments; exact authorization evidence is retrieved by `Day0ReadinessAssessment` ID.

Exact replay reused the same four IDs and fingerprints with no duplicate derived artifact.
