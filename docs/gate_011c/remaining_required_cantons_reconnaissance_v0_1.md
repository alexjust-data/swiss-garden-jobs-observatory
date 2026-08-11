# GATE-011C-3 remaining required cantons reconnaissance v0.1

Observed on 2026-08-11. Live counts are evidence only and are never production constants.

## Phase A matrix

| Source | Frozen family | Verified live platform | Governed surfaces | Access | Reuse cluster | Terminal state |
|---|---|---|---|---|---|---|
| `SRC-OFF-CANTON-AI` | `OFFICIAL_WEB` | Plone landing plus Abacus Jobportal | ordinary jobs; canton-employer apprenticeships | origins readable, complete cross-surface vacancy identity unresolved | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-FR` | `FR_MIGRATION_PORTAL` | SAP SuccessFactors plus legacy ProRecrute and separate education surfaces | ordinary/police; legacy vacancies; apprenticeships/practica; teaching | public pages readable, complete multi-platform universe unresolved | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-GL` | `UMANTIS_LINKED` | Umantis plus official static pages/PDF | ordinary; apprenticeships; practica/standing legal internship | public evidence readable, no unified publication identity/exhaustion contract | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-GR` | `CANTON_GR_PORTAL` | Refline tenant `514915` | ordinary; apprenticeships; trial apprenticeships | robots permits tenant; static GET contract | Refline | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-JU` | `OFFICIAL_WEB` | Jura custom CMS lists | administration; teaching; magistracy; other; apprenticeships/stages; teacher replacements | public lists readable, complete category/replacement contract unresolved | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-NW` | `CANTON_NW_PORTAL` | WordPress/Elementor custom content | ordinary; police; apprenticeships/practicum | robots permits; training pages expose profiles/availability rather than stable vacancy publications | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-OW` | `OFFICIAL_WEB` | i-web CMS plus separate recruiting surfaces | ordinary; vocational training/practicum; police | mandatory surfaces visible, complete stable publication contract unresolved | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-SH` | `OFFICIAL_WEB` | K4/CMS client-rendered page | canton-employer vacancies | robots allows, server HTML exposes no auditable vacancy identity/feed | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-SO` | `CANTON_SO_PORTAL` | Prospective Career Center `1001566` | one unified feed including professionals, teachers, learners and practica | robots allows; static GET and canonical detail GET | Prospective configured | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-SZ` | `CANTON_SZ_PORTAL` | Prospective Career Center `1677` | one unified categorized feed including administration, schools, practica and vocational training | robots allows; static GET/POST pagination and detail GET | Prospective configured | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-TG` | `CANTON_TG_PORTAL` | Govis listing with Prospective details plus separate Govis training site | ordinary; apprenticeships; practica | origins readable, training pages are profiles and secondary vacancy exhaustion is unresolved | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-UR` | `OFFICIAL_WEB` | i-web official site | ordinary; apprenticeships referenced from employer training page | origin was unavailable during controlled verification; no complete contract promoted | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-VS` | `OFFICIAL_WEB` | Liferay plus e-recruitment and official-gazette teaching search | ordinary; teaching; apprenticeships/stages | public landing readable, mandatory cross-platform universe cannot be reconciled under governed HTTP | blocked | `ACCEPTED_BLOCKED` |

## Verified platform clusters

### Refline

- Sources: `SRC-OFF-CANTON-GR`.
- Common contract: tenant-scoped, complete in-memory HTML listings with stable numeric publication IDs and canonical Refline details carrying `JobPosting` JSON-LD.
- Shared implementation: `GraubuendenReflineAdapter`, configured with the exact tenant and all three governed surfaces.
- Source-specific configuration: tenant `514915`; `search.html`, `apprentice.html`, and `stage.html`.

### Prospective configured legacy

- Sources: `SRC-OFF-CANTON-SO`, `SRC-OFF-CANTON-SZ`.
- Common contract: UUID detail identity, server-visible listing form, `JobPosting` JSON-LD details.
- Shared implementation: the validated Prospective parser and detail translator; exact-source subclasses retain their frozen platform family.
- Source-specific configuration: SO is one complete 1000-capacity feed with reported-total equality; SZ is an eight-row page contract with exact offset progression and next-page exhaustion.

### Blocked

The remaining ten sources are not promoted. No adapter, `SourceEndpoint`, or production collection run is created for them. They remain `DAY0_REQUIRED` and preserve the 29-source denominator.

## Implemented source contracts

### Graubünden

- Official landing: `https://stellen.gr.ch/`, redirecting to `https://apply.refline.ch/514915/search.html`.
- Listing/detail origin: `apply.refline.ch`; assets on `cdn.refline.ch` are not required for collection.
- Surfaces: ordinary (`search.html`), apprenticeships (`apprentice.html`), trial apprenticeships (`stage.html`).
- Native identity: the stable numeric Refline publication component immediately after tenant `514915`.
- Canonical detail: `/514915/<publication-id>/pub/<publication-channel>/index.html`.
- Exhaustion: every surface is a complete server-rendered table; absence text is an explicit empty terminal state.
- Languages: de/rm/it/fr are presentation variants of the same tenant IDs; German is the governed discovery presentation and does not filter the economic publication set.
- Publication: JSON-LD `datePosted`; update timestamp is not invented.
- Geography: JSON-LD address only.
- Robots: `apply.refline.ch/robots.txt` allows this tenant; only unrelated `/rec01/1/` and `/rec03/1/` paths are disallowed.

### Solothurn

- Official portal/listing/detail origin: `job.so.ch`.
- Universe: the root feed visibly includes ordinary, teacher and apprenticeship records and exposes profession/learner/practicum categories in the same form.
- Native identity: UUID in the canonical detail path.
- Exhaustion: reported total equals the complete root response (form limit 1000); capacity overflow fails closed.
- Publication/geography: detail JSON-LD only.

### Schwyz

- Official portal/listing/detail origin: `jobs.sz.ch`.
- Universe: the root form exposes employment categories including `Praktikum` and `Berufslehre`, and employer groups including the cantonal administration and cantonal schools.
- Native identity: UUID in the detail path.
- Exhaustion: offsets advance exactly by eight until no enabled higher page remains. A jump, repeat, or non-advancing page fails closed.
- Publication/geography: detail JSON-LD only.

## Blocked source evidence

All blocked conclusions mean zero production requests, endpoints, adapters and collection runs.

- AI: the ordinary Plone view delegates to `stellen.ai.ch` (Abacus), while canton-employer apprenticeship openings are published as cohort counts on a separate official page. No stable common vacancy-publication identity or complete unified exhaustion proof was available.
- FR: SuccessFactors locale variants are presentation views, but the canonical employment hub also points to legacy ProRecrute and separately governed teaching/training surfaces. Collecting only SuccessFactors would be partial.
- GL: ordinary vacancies use Umantis, while apprenticeships and practica include official static pages and a standing legal-internship PDF. Profiles and a standing PDF cannot be silently recast as vacancy IDs.
- JU: the official CMS exposes separate administration, education, magistracy, other, apprenticeship/stage and replacement-teacher channels. The frozen URL has also migrated. No complete cross-channel identity contract was proven.
- NW: ordinary `/stelle/` publications are distinct from apprenticeship/practicum profile pages that show yearly availability. The latter are not stable vacancy publications.
- OW: ordinary, vocational/practicum and police recruitment are separate mandatory surfaces; their current server contract does not expose one verifiable source-native universe.
- SH: robots allows access, but the large CMS shell provides no server-visible vacancy rows or official static/API feed. Production browser automation is outside this gate.
- TG: the ordinary Govis list links to Prospective UUID details, while `lernende.tg.ch` exposes occupational profiles (including gardener) and practica is separate. A profile is not vacancy identity.
- UR: the official origin was unavailable in repeated verification and the apprenticeship page delegates openings to the jobs surface. Access and completeness could not be verified, so no endpoint was promoted.
- VS: the Liferay page separates general e-recruitment, teaching publications in the official gazette, and apprenticeships/stages. Language URLs do not establish separate identities, but the mandatory technical surfaces remain irreconcilable.

## Boundary exclusions

Municipal employers, universities, hospitals, public corporations, independent schools and courts are excluded unless the observed portal itself presents them as members of the same canton-employer vacancy universe. No external link was absorbed merely because it appeared on a canton website.

Previously blocked AG, BE, LU, SG canton and Stadt St. Gallen were not revisited. Job-Room and Job-Room API were not activated. Threshold and freshness policies remain `PENDING`; no Day-0 market figure is authorized.

## Controlled live acceptance

| Source | Run | Listing requests | Unique IDs / details / observations / green | Green distribution | Publication | Municipality | Result |
|---|---|---|---|---|---|---|---|
| GR | `cebbd705-9cc6-4f40-89a7-aa3b274c7d1a` | ordinary 1; apprenticeships 1; trial apprenticeships 1 | 40 / 40 / 40 / 40 | 0 confirmed; 4 review; 36 not green | 40 `EXACT_DATETIME/STRUCTURED_DATA` | 36 exact; 4 unresolved | `SUCCEEDED/HEALTHY/complete` |
| SO | `aa7f3fd5-aa9d-4fb1-808b-ebe42f637302` | unified 1 | 27 / 27 / 27 / 27 | 0 confirmed; 2 review; 25 not green | 27 `EXACT_DATE/STRUCTURED_DATA` | 0 exact; 27 unresolved | `SUCCEEDED/HEALTHY/complete` |
| SZ | `2a18933d-35b2-433d-842d-89375540b901` | unified 4 | 27 / 27 / 27 / 27 | 0 confirmed; 0 review; 27 not green | 27 `EXACT_DATE/STRUCTURED_DATA` | 0 exact; 27 unresolved | `SUCCEEDED/HEALTHY/complete` |

All 94 observations produced one green assessment and one `NEW` lifecycle event. Cross-surface duplicates were zero. Negative lifecycle evidence was zero. A first SO attempt failed closed before observation creation because live title markup differed from the inherited parser; the accepted run above uses the source-specific observed contract and preserves that failed run as historical evidence.
