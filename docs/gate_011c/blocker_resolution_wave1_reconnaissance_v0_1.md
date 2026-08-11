# GATE-011C-4 blocker resolution wave 1 reconnaissance v0.1

Observed on 2026-08-11. Live counts and availability are time-bound evidence, never production constants. Phase A covered all six sources before implementation.

## Source and surface matrix

| Source | Surface | Platform / employer | Entity classification | Identity, access and completeness | Decision |
|---|---|---|---|---|---|
| AI | ordinary, `https://stellen.ai.ch/` | Abacus Jobportal / Kanton AI | `UNRESOLVED` | public SPA, but `api.jobportal.abaservices.ch/api` tenant and robots requests required authentication; identity/exhaustion not inspectable | blocked |
| AI | canton apprenticeships | Plone/HTML / Kanton AI | `UNRESOLVED` | profession/year/department cohort rows show capacity such as open places but no stable vacancy publication ID or canonical detail | blocked |
| AI | broad apprenticeship directory | Plone / multiple employers | `SEPARATE_EMPLOYER_SOURCE` | directory includes private and public employers outside the canton-employer boundary | exclude |
| LU | administration, `https://apply.refline.ch/891537/positions_verwaltung.html` | Refline / Kanton LU | `VACANCY_SOURCE_SURFACE` | numeric ID; `/891537/<id>/pub/<channel>/index.html`; complete in-memory list or explicit empty marker | include |
| LU | cantonal schools/teachers, `positions_lehrpersonen.html?businessUnit=lehrpersonal` | Refline / Kanton LU | `VACANCY_SOURCE_SURFACE` | same tenant identity; second mandatory complete list | include |
| LU | `https://lehre.lu/api/web/jobs` and `/api/web/jobs/<profile>` | Nuxt JSON / Kanton LU | mixed surface: open profile = `VACANCY_SOURCE_SURFACE` | complete feed reports 83 profiles at observation time; 29 `free=true`; admitted detail must expose canonical profile plus tenant-891537 `link_job` application action | include active opportunities |
| LU | inactive evergreen profile on `https://lehre.lu/map/<profile>` | Nuxt profile / Kanton LU | `NON_VACANCY_SOURCE_SURFACE` state | `free=false`; profile remains published without a current application opportunity | exclude before Posting |
| LU | Schnupper action/content on an apprenticeship profile | orientation mechanism / Kanton LU | `NON_VACANCY_SOURCE_SURFACE` aspect | trial request is distinct from the real Lehrstelle application; never creates a second Posting | exclude before Posting |
| LU | higher-education practica information | official HTML / Kanton LU | `NON_VACANCY_SOURCE_SURFACE` | page says advertised practica appear in the ordinary Stellenmarkt | no extra seed |
| LU | municipal/music-school jobs | external local employers | `SEPARATE_EMPLOYER_SOURCE` | independent employer publications | exclude |
| SG | governed `recruitingapp-2800.umantis.com/Jobs/All` CompanyID set | Umantis / Kanton SG units | `VACANCY_SOURCE_SURFACE` | numeric `/Vacancies/<id>/Description/1`; 25-row monotonic pages; stable total; terminal range equality | include |
| SG | training/careers pages | official HTML / Kanton SG | `NON_VACANCY_SOURCE_SURFACE` | profiles; actual apprenticeships, practica and entry roles are publications in unified Umantis | no extra seed |
| SG | Schnupper opportunities | orientation portal / training units | `NON_VACANCY_SOURCE_SURFACE` | orientation experience, not employment vacancy | exclude before Posting |
| SG | city vacancies | independent city portal / Stadt SG | `SEPARATE_EMPLOYER_SOURCE` | remains frozen separate blocked Source | exclude |
| JU | administration | Jura CMS `JobList` / canton | `VACANCY_SOURCE_SURFACE` | numeric `?ID=<id>` and specific detail are observable | whole source still blocked |
| JU | magistracy | Jura CMS / judiciary | `VACANCY_SOURCE_SURFACE` | category exposes explicit empty state | include only if whole source resolves |
| JU | teaching | Jura CMS / canton education | `UNRESOLVED` | observed response has neither entries nor explicit empty/module marker; zero cannot be distinguished from missing feed | blocked |
| JU | other jobs | Jura CMS / potentially multiple employers | `UNRESOLVED` | employer boundary and explicit exhaustion remain unresolved | blocked |
| JU | annual apprenticeship/stage information | Jura CMS / canton | `NON_VACANCY_SOURCE_SURFACE` | annual offering/profile; one-to-three-day observation stages are orientation, not vacancy | exclude |
| JU | teacher replacement registration | CMS/form / candidate pool | `NON_VACANCY_SOURCE_SURFACE` | standing candidate registration, not a specific replacement opening | exclude |
| NW | ordinary `/stelle/` and `live.solique.ch/KTNW/de/#/` | WordPress/Solique / Kanton NW | `VACANCY_SOURCE_SURFACE` | publication identity observable, but mandatory training boundary remains unresolved | blocked, no partial promotion |
| NW | police careers | informational HTML / canton police | `NON_VACANCY_SOURCE_SURFACE` | evergreen/contact profiles, no specific opening | exclude |
| NW | apprenticeships/practica | training pages / Kanton NW | `UNRESOLVED` | profession/year availability indicates opportunity but supplies no vacancy-level canonical publication | blocked |
| TG | `https://stellen.tg.ch/` and `/stellen.html/1917/pjobpage/N` | Govis + Prospective / canton and external institutions | boundary feed | reported-total equality and exact pages; reconcile against external category | mandatory input |
| TG | POST category 28, Externe Institutionen | Govis / separate employers | `SEPARATE_EMPLOYER_SOURCE` | independently exhausted UUID set; subtract before detail/Posting promotion | exclude |
| TG | unified IDs minus category-28 IDs | Govis/Prospective / Kanton TG | `VACANCY_SOURCE_SURFACE` | stable UUID `/public/v1/jobs/<uuid>`; both feeds must complete | include |
| TG | `https://lernende.tg.ch/` | Govis profile site / training information | `NON_VACANCY_SOURCE_SURFACE` | occupation/profile identity, including gardener, is not a vacancy publication | exclude before Posting |
| TG | practica information | official HTML / Kanton TG | `NON_VACANCY_SOURCE_SURFACE` | actual advertised practica are in the unified feed | no extra seed |

## Phase A terminal decisions

| Source | Verified platform | Source-universe conclusion | Cluster | Terminal state |
|---|---|---|---|---|
| `SRC-OFF-CANTON-AI` | Plone + Abacus | ordinary API and apprenticeship publication identity unresolved | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-LU` | Refline tenant 891537 + official Nuxt JSON | administration + cantonal schools/teachers + active in-scope apprenticeships; inactive/profile/Schnupper content excluded | Refline + Nuxt API | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-SG` | Umantis | unified actual-vacancy feed includes ordinary, teachers, apprenticeships and practica | Umantis | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-JU` | Jura CMS | teaching/other completeness or employer boundary unresolved | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-NW` | WordPress/Solique + profiles | training availability lacks stable vacancy publications | blocked | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-TG` | Govis + Prospective | exhaust unified and external category, promote only canton UUIDs | boundary adapter | `ACCEPTED_IMPLEMENTED` |

## Verified implementation clusters

### Refline + Nuxt JSON — Luzern

The exact-source adapter has three mandatory complete listing surfaces. The two Refline
lists preserve their numeric publication identities. The official JSON feed proves its
profile total before filtering; only `free=true` rows become candidates, and every
candidate detail must still be open and expose a governed tenant-891537 application
action. Source-native identity is `lehre:<profile_id>`; the evergreen
`/map/<profile_id>` page is its corroborating canonical URL and the Refline application
code proves current application state. Profile `updated_at` is stored only as update
evidence. The API exposes location title, city and postal code but no canton field, so
raw `location_region` is empty and governed geography resolves downstream. Identical
Refline native ID/detail pairs collapse and conflicts fail closed. Failure of any of the
three surfaces fails the FULL_SOURCE run.

### Umantis — St. Gallen canton

The official employer landing points to one server-readable Umantis contract whose filters include teaching, apprenticeships, practica and early-career roles. Pagination state must advance exactly, totals remain stable, and the final range must equal the total. Authorization is exact to canton SG and does not authorize Stadt St. Gallen or another Umantis source.

### Govis/Prospective boundary — Thurgau

The Govis list is broader than the frozen direct-public-employer Source and explicitly labels category 28 as external institutions. The adapter preserves RAW evidence while exhausting the unified list, then POSTs and exhausts category 28. External UUIDs are removed before detail or Posting promotion. Failure of either feed fails the FULL_SOURCE run.

## Access, identity and semantic safeguards

- LU Refline and `lehre.lu/api/web/jobs` paths are server-readable and not prohibited
  by the applicable robots evidence. No browser execution is used in production.
- SG Umantis robots restrictions do not prohibit the public `Jobs`/`Vacancies` paths.
- TG robots excludes `/route/`, not the governed listing; the Prospective public detail contract is readable.
- AI's mandatory API required authentication, so no endpoint or run was promoted.
- JU/NW readability does not cure their identity and universe blockers.

Production uses governed GET/POST only. Profession, year, row and category are never
fabricated into vacancy identity. LU's API-provided stable profile ID is preserved as
`lehre:<profile_id>`; it is not derived from title or position. Profile `updated_at`
is not publication time. Raw region is never inferred from the canton employer Source.
Municipality comes only from published city/postcode evidence through governed
resolution. Non-vacancy exclusion occurs before Posting and green classification.

Recurrence is covered by the closed GATE-008 regression
`test_same_posting_reappearance_creates_one_new_episode`: stable Posting, governed
close, same Vacancy on reappearance, Episode 2 and one `REAPPEARED` event.

AI, JU and NW receive no C-4 adapter, endpoint or authoritative run. AG, BE, FR, GL, OW, SH, UR, VS, Stadt SG, Job-Room and Job-Room API remain outside scope and inactive. Threshold/freshness remain `PENDING` and Day-0 remains unauthorized.

## Controlled live acceptance

| Source | Run | Listing requests | Reconciliation | IDs / details / observations / green | Green distribution | Publication | Municipality | Result |
|---|---|---|---|---|---|---|---|---|
| LU | `90cfcdf2-06f0-459e-aebd-e9867f2d335d` | administration 1; cantonal schools 1; apprenticeship API 1 | 43 + 2 + 29 open; 54 inactive profiles excluded; Schnupper creates no Posting | 74 / 74 / 74 / 74 | 0 confirmed; 0 review; 74 not green | 45 `EXACT_DATETIME/STRUCTURED_DATA`; 29 `UNKNOWN/MISSING` with update evidence separate | 72 exact; 2 unresolved | `SUCCEEDED/HEALTHY/complete` |
| SG | `95bc8a59-3b12-4852-a469-607432eb700b` | unified 4 | reported total 79 | 79 / 79 / 79 / 79 | 0 confirmed; 6 review; 73 not green | 79 `UNKNOWN/MISSING` | 28 exact; 51 unresolved | `SUCCEEDED/HEALTHY/complete` |
| TG | `846a4c5c-7b79-4708-afe6-81d13b4de161` | unified 2; external employers 1 | unified 40; external 5; 35 promoted | 35 / 35 / 35 / 35 | 0 confirmed; 1 review; 34 not green | 35 `EXACT_DATE/STRUCTURED_DATA` | 0 exact; 35 unresolved | `SUCCEEDED/HEALTHY/complete` |

The corrected final runs contain 188 accepted observations and exactly one green
assessment per observation. The latest LU run records one `NEW` Posting and 73
`STILL_ACTIVE` Postings; SG/TG retain their accepted lifecycle evidence.
Negative lifecycle evidence is zero.

The earlier LU runs remain immutable superseded evidence. Run
`7c05bffe-1ace-4a8c-874d-ad61a63d191e` omitted the mandatory apprenticeship surface;
run `edaa2996-9395-41e0-9674-78b40179d1f8` admitted that surface but populated raw
`location_region=LU` without source canton evidence. The authoritative run above keeps
all 29 apprenticeship regions empty while resolving all 29 municipalities from explicit
city/postcode evidence.

The first SG attempt, `4a6eeb0f-2e60-4933-a4eb-9b635a33be64`, remains immutable failed evidence. It exposed that the first Umantis page serializes pagination values as JSON numbers while later pages serialize the same non-negative decimal values as strings. The accepted parser normalizes only those two proven representations and still enforces exact page progression, stable total and terminal range equality. The failed run has `snapshot_complete=false` and created no observations or lifecycle truth.
