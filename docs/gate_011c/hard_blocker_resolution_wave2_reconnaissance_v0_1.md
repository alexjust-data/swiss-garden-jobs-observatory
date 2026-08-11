# GATE-011C-5 hard-blocker resolution — reconnaissance v0.1

Observed on 2026-08-11. Live counts below are evidence, never configuration. The
merged baseline is `bbd4ea637878fed1388c0f14d03ec5fba097f956`.

## Phase-A matrix

| Source | Current official platform | Vacancy surfaces | Official origins | Access / robots / auth | Native identity and exhaustion | Employer boundary | Cluster | Terminal state | Remaining blocker |
|---|---|---|---|---|---|---|---|---|---|
| `SRC-OFF-CANTON-AG` | canton React component backed by Umantis proxy | administration, courts, police, canton schools, apprenticeships | `www.ag.ch`; observed `jobs.ag.ch` alternate returned an empty response | `www.ag.ch/robots.txt` explicitly disallows `/io/*`; no auth-free independent complete ATS listing was proven | proxy identity exists but complete feed cannot be requested under policy | school employers remain part of the official hub boundary | blocked | `ACCEPTED_BLOCKED` | `ROBOTS_BLOCKED`, `EXHAUSTION_UNPROVEN` |
| `SRC-OFF-CANTON-BE` | Prospective plus KSML/STEZE teaching applications | ordinary, apprenticeships/practica, teachers, substitute teachers | `www.jobs.apps.be.ch`, `ksml.apps.be.ch`, `steze.apps.be.ch` | Prospective surfaces are public; KSML is a client shell and its robots request returned 403; STEZE returned 403 | Prospective UUIDs are strong, but mandatory teaching surfaces cannot be exhausted | all four channels are presented by the canton employer hub | blocked | `ACCEPTED_BLOCKED` | `HTTP_403`, `MULTI_SURFACE_INCOMPLETE` |
| `SRC-OFF-CANTON-FR` | SuccessFactors migration plus legacy ProRecrute and separate teaching/training channels | current SPE/Police/SITel jobs, other administration jobs, teaching, initial training/stages | `jobs.fr.ch`, `adm.appls.fr.ch`, linked official teaching origins | public pages exist; no one authorized contract reconciles every mandatory surface | multilingual/migration identity and cross-platform exhaustion remain unproven | linked teaching/training channels require complete canton-employer reconciliation | blocked | `ACCEPTED_BLOCKED` | `PLATFORM_IDENTITY_UNRESOLVED`, `MULTI_SURFACE_INCOMPLETE`, `EXHAUSTION_UNPROVEN` |
| `SRC-OFF-CANTON-GL` | public Umantis tenant 2910 | one unified list containing ordinary jobs, actual apprenticeships and training positions | `www.gl.ch`, `recruitingapp-2910.umantis.com` | canton robots allows the relevant page; Umantis listing/details are public and its robots response did not publish a prohibition of them | numeric `/Vacancies/<id>/Description/1`; `table-navigation` reported total and monotonic page state; observed total 20 | static profession/training pages are information; actual openings are present in unified Umantis | Umantis public HTML | `ACCEPTED_IMPLEMENTED` | none |
| `SRC-OFF-CANTON-OW` | official i-web page embedding Zentraljob minisite 9 | ordinary, actual apprenticeships, police; separate training/profile information | `www.ow.ch`, `management.zentraljob.ch` | `management.zentraljob.ch/robots.txt` says `Disallow: /` | numeric detail IDs are visible, but the mandatory listing cannot be authorized | career/profile pages are not promoted; the blocked listing contains actual openings | blocked | `ACCEPTED_BLOCKED` | `ROBOTS_BLOCKED` |
| `SRC-OFF-CANTON-SH` | official public Umantis tenant 2876 | unified ordinary, apprenticeship, police and practicum list | `sh.ch`, `recruitingapp-2876.umantis.com` | official page links the tenant; robots disallows only unrelated private/import/subscription paths | numeric `/Vacancies/<id>/Description/1`; reported total and monotonic table state; observed total 18 | canton portal is the authoritative employer surface; city Schaffhausen remains separate | Umantis public HTML | `ACCEPTED_IMPLEMENTED` | none |
| `SRC-OFF-CANTON-UR` | i-web server-rendered localdynamic table and detail pages | unified current openings; apprenticeship/profile PDF is informational and current openings belong in the table | `www.ur.ch`, application action on `jobs.ur.ch` | robots is empty and no auth is required, but detail delivery repeatedly timed out during controlled acceptance | table embeds the complete row set and numeric identity, but the origin did not sustain a complete detail pass | table rows are canton employer openings; static profession capacity is not a vacancy | blocked | `ACCEPTED_BLOCKED` | `ORIGIN_UNAVAILABLE` |
| `SRC-OFF-CANTON-VS` | Liferay landing, e-recruitment, official-gazette teaching, apprenticeship/stage channels | administration, teaching, apprenticeships/stages | `www.vs.ch`, e-recruitment and official gazette origins | public entry points exist; no single static/API contract proves all mandatory surfaces | FR/DE publication reconciliation and cross-platform exhaustion remain unproven | teaching and training channels require per-publication employer reconciliation | blocked | `ACCEPTED_BLOCKED` | `MULTI_SURFACE_INCOMPLETE`, `EXHAUSTION_UNPROVEN`, `PLATFORM_IDENTITY_UNRESOLVED` |
| `SRC-OFF-CITY-STGALLEN` | Solique modern API tenant `STSG` | unified ordinary, apprenticeships, practica, schools/police and technical works | `www.stadt.sg.ch`, `live.solique.ch` | official page embeds Solique; Solique robots allows `/`; no authentication | `title.id` numeric publication ID; one in-memory feed with position total; observed total 42 | official city page describes roads, electricity and city parks as work for the city, corroborating city and Stadtwerke entries in one canonical employment surface | Solique modern API | `ACCEPTED_IMPLEMENTED` | none |

## Access decisions

- No request to the prohibited Aargau `/io/*` proxy is authorized.
- No production request to Obwalden's Zentraljob tenant is authorized after its
  blanket robots prohibition was established.
- Bern, Fribourg and Valais remain required. An accessible subset cannot be
  promoted as `FULL_SOURCE`.
- No authentication token, browser session, browser execution, mirror, or
  alternate user agent is used.

## Implemented clusters

### Public Umantis HTML

Sources: Glarus and Schaffhausen canton.

Shared contract: source-specific official tenant; numeric vacancy ID; public
server-rendered listing and detail; `table-navigation` stable total; page/range
and next-token progression. Tenant URL, table number and page size remain live
contract evidence rather than global Umantis authorization.

### Solique modern API

Source: Stadt St. Gallen.

The existing modern Solique parser contract is configured for exact source
tenant `STSG`. The feed itself contains ordinary jobs, apprenticeships and
practica, so category filtering is neither required nor permitted.

## Evidence notes

- Glarus observed list: `20/20`, including specific apprenticeship and training
  publications with per-vacancy application actions.
- Schaffhausen observed list: `18/18`, including an apprenticeship, a police
  school opening and a legal practicum.
- Uri exposed ten stable numeric rows during reconnaissance, but two controlled
  FULL_SOURCE attempts timed out while fetching official details. Both runs are
  failed/incomplete historical evidence. No production adapter or endpoint is
  promoted.
- Stadt St. Gallen observed feed: `42`, split by the source into ordinary,
  learners and practica categories and including a live gardener publication.
- Observed totals can change at any time. Completeness is established by the
  structural total/exhaustion contracts above.

## Controlled acceptance

- Glarus run `3dcb6342-90af-47f6-8701-a18a0f250c29` is
  `SUCCEEDED / HEALTHY / snapshot_complete=true`: one listing plus 20 detail
  requests, `20/20/20/20` IDs/details/observations/green assessments, green
  distribution `1/1/18` (`GREEN_CONFIRMED/REVIEW/NOT_GREEN`) and 20 `NEW`.
- Schaffhausen run `47f65919-1f5b-4a4d-b4d7-f5d9d2472d45` is
  `SUCCEEDED / HEALTHY / snapshot_complete=true`: one listing plus 18 detail
  requests, `18/18/18/18`, green distribution `0/0/18` and 18 `NEW`.
- Stadt St. Gallen run `80079285-ade8-498c-8550-f006f62d4051` is
  `SUCCEEDED / HEALTHY / snapshot_complete=true`: one listing plus 42 detail
  requests, `42/42/42/42`, green distribution `1/1/40`, 16 `NEW` and 26
  `STILL_ACTIVE`.
- Uri runs `d918659c-d118-48a5-9cdf-349f3e7fdad6` and
  `8ea56782-5d99-4773-b0c8-cb7086eecee8` are retained as
  `FAILED / DEGRADED / snapshot_complete=false` evidence. Current production
  state is zero endpoints and no adapter.
- All 80 accepted C-5 observations use publication provenance `MISSING`,
  preserve empty raw `location_region`, and remain municipality-unresolved.
  No publication time or workplace geography is inferred from source identity.

## Isolation

`AI`, `JU`, and `NW` retain their C-4 blocked outcomes. Job-Room and Job-Room
API remain outside scope. Canton St. Gallen authorization does not authorize
Stadt St. Gallen; the city receives its own exact source/tenant decision here.
