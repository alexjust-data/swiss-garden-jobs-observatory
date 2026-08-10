# GATE-011C-1 required canton reconnaissance v0.1

Reconnaissance date: 2026-08-10. Official endpoints only.

| Source | Frozen family | Verified contract | Authorized origins | Pagination/completeness | Strategy | Terminal target |
|---|---|---|---|---|---|---|
| `SRC-OFF-CANTON-ZH` | `SOLIQUE_LINKED` | Solique `KTZH` JSON API plus Solique detail | `www.zh.ch`, `live.solique.ch` | API job universe; `filters.position.count` must equal unique IDs | New reusable Solique API translator | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-AR` | `SOLIQUE_EMBEDDED` | Solique legacy `api/json/` plus `Microsites/showPublication` | `ar.ch`, `live.solique.ch` | Client-side feed contains complete job array | New reusable Solique legacy translator | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-ZG` | `PROSPECTIVE` | Prospective legacy listing plus official `www.zg.ch` JSON-LD detail | `zg.ch`, `zg.prospective.ch`, `www.zg.ch` | POST offsets of 10 until no forward page | Configured shared Prospective translator | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-BL` | `PROSPECTIVE_UMANTIS_LINKED` | Prospective career center plus official `jobs.baselland.ch` JSON-LD detail | `www.baselland.ch`, `ohws.prospective.ch`, `jobs.baselland.ch` | POST offsets of 15; reported total must equal unique IDs | Configured shared Prospective translator; Umantis not authorized | `ACCEPTED_IMPLEMENTED` |

## Identity and evidence

- Zurich: `title.id` is the source publication identity. The API supplies title, organization, office, location, modification evidence and job HTML. `dateModified` is not treated as publication evidence.
- Appenzell Ausserrhoden: `sPublicationId` is the source publication identity. `deepLink` remains on `live.solique.ch`; `startDate` and `dateModified` retain separate provenance.
- Zug and Basel-Landschaft: the terminal UUID in the official detail URL is the source publication identity. Details expose `JobPosting` JSON-LD with publication and location evidence.

## Access result

All four official contracts were readable under their recorded automation-review requirement. Implementation remains acknowledgement-gated. Robots evidence did not prohibit the verified listing/detail paths. No redirect or request to an unregistered origin is permitted.

## Platform mismatch result

No material frozen/live family mismatch was found. The labels describe vendors, not identical wire formats, so source-specific configuration is retained inside two shared vendor modules rather than forcing one parser contract.

## Day-0

These sources remain required identities regardless of operational outcome. Threshold and freshness policy remain pending, and no Day-0 figure is authorized by this artifact.

## Zug source-universe correction

The official Kanton Zug employment hub separates ordinary vacancies from
apprenticeships. The frozen registry contains one canonical
SRC-OFF-CANTON-ZG identity and no separate apprenticeship Source, so both
surfaces are in scope:

| Surface | Governed listing | Pagination | Native identity |
|---|---|---|---|
| Ordinary jobs | https://zg.prospective.ch/ | GET then Prospective POST offsets | terminal UUID |
| Apprenticeships | https://zg.prospective.ch/lernende/ | GET then Prospective POST offsets | terminal UUID |

Both use official www.zg.ch detail URLs and JobPosting JSON-LD. At
reconnaissance time the root exposed 18 identities over offsets 0 and 10,
the apprenticeship surface exposed three identities on its first page, and
the two sets did not overlap. These are observations, not hard-coded expected
counts. The adapter exhausts both surfaces, reconciles equal UUID/detail pairs,
fails on conflicting identities or a missing surface contract, and records
every request through the shared pipeline.

The prior root-only 18-record run 7bdab80c-4d12-4baa-b627-23e54758f70a
remains immutable historical evidence but is superseded for gate acceptance.

## Corrected live acceptance

The corrected FULL_SOURCE Zug run
`00f00469-6109-447f-8718-23590f00e5bb` started at
`2026-08-10T21:49:40.457034+00:00` and finished at
`2026-08-10T21:50:19.362094+00:00`. It persisted three listing fetches:

1. ordinary GET at `https://zg.prospective.ch/`;
2. ordinary POST at the same URL with offset 10;
3. apprenticeship GET at `https://zg.prospective.ch/lernende/`.

The ordinary surface exposed 18 identities and the apprenticeship surface
three. Their intersection was empty, producing 21 unique native IDs, 21
details, 21 PostingObservations and 21 GreenRelevanceAssessments. The green
distribution was 0 GREEN_CONFIRMED, 1 REVIEW and 20 NOT_GREEN. All 21
publication dates came from structured `JobPosting.datePosted` evidence with
EXACT_DATE precision. Municipality resolution remained unresolved for all 21;
no canton-to-municipality inference was made. The run was SUCCEEDED, HEALTHY
and `snapshot_complete=true`, with no negative lifecycle evidence.

The shared Prospective change was regressed live against Basel-Landschaft.
BL uses its own verified `oh-form` contract marker, while Zug uses
`careercenter-form`; either adapter fails closed when its marker is absent.
The successful BL regression run
`6f40e61d-635a-4c00-843e-ade99fe2b33e` finished at
`2026-08-10T22:05:55.884949+00:00`: four listing requests, 48 unique IDs,
48 details, 48 observations and 48 green assessments; 0 GREEN_CONFIRMED,
1 REVIEW and 47 NOT_GREEN; SUCCEEDED, HEALTHY and complete. Its fetch evidence
contains zero Umantis requests. Accepted Solique evidence for Zurich
(`3a9d318a-0afb-4b33-a22d-53599e8cf8af`) and Appenzell Ausserrhoden
(`3ff09ba0-5965-444a-b377-edcdb820fe14`) was preserved without unnecessary
recollection.

## Aligned downstream replay

The final shared point-in-time is the successful BL regression finish,
`as_of=2026-08-10T22:05:55.884949+00:00`. The exact aligned artifacts are:

- DedupRun `f5674998-5ea2-4153-930d-a1b9d8420bdc`: 903 selected postings,
  903 effective vacancies, 0 AUTO_MERGE and 7 REVIEW pairs.
- PremiumSegmentRun `b239ca08-f1fb-4eac-9254-d38516458805`: 903 observations,
  11 green-eligible and 892 skipped as not green.
- DashboardSnapshot `30203333-739f-4719-81c8-e574142bb373`: 11 public green
  vacancies, 30 review-not-public, 0 safely mappable and 11 unmappable.
- Day0ReadinessAssessment `aa537bb3-18df-497a-bf94-4b26f58b2158`: required
  complete 9/29, required healthy 9/29, coverage
  `0.3103448275862068965517241379`, 30 critical green reviews and status
  DAY_0_THRESHOLD_POLICY_PENDING.

An exact second replay reused all four IDs and input fingerprints. Threshold
policy and freshness policy remain PENDING. No market figure is authorized.
