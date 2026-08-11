# GATE-011C-2 major required sources — reconnaissance v0.1

Observed on 2026-08-11. Counts are time-bound evidence, never production constants. The
frozen Source registry was not changed.

## Summary

| Source ID | Frozen family | Verified platform/vendor | Governed vacancy surfaces | Access | Terminal state |
| --- | --- | --- | --- | --- | --- |
| `SRC-OFF-JOBS-ADMIN` | `FEDERAL_JOB_PORTAL` | Prospective public v1 Career Center `1000624` | One unified unfiltered feed; UI tabs are filters | allowed | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-AG` | `CANTON_AG_PORTAL` | Aargau React component over official Umantis proxy | ordinary jobs, internships and apprenticeships in proxy; school link is a separate employer market | prohibited feed | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-BE` | `SITES_BE` | Prospective plus separate teaching applications | ordinary, apprenticeships, teachers, substitute teachers | unresolved mandatory origins | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-BS` | `BS_EMPLOYER_PORTAL` | current Solique-rendered employer market; legacy SuccessFactors still observable | ordinary jobs; apprenticeships | allowed | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-LU` | `CANTON_LU_PORTAL` | Refline plus `lehre.lu` Nuxt | administration, cantonal teaching/pedagogy, apprenticeships | apprenticeship identity unresolved | `ACCEPTED_BLOCKED` |
| `SRC-OFF-CANTON-SG` | `CANTON_SG_PORTAL` | Umantis plus separate education/training surfaces | administration, internships, apprenticeships, teachers | only one sub-surface resolved | `ACCEPTED_BLOCKED` |

## `SRC-OFF-JOBS-ADMIN`

- Official landing: `https://jobs.admin.ch/`.
- Verified platform: Prospective Career Center `1000624`.
- Listing/API origin: `https://ohws.prospective.ch/public/v1/medium/1000624/jobs`.
- Detail origin: `https://jobs.admin.ch/offene-stellen/.../<viewkey>`.
- Source universe: the UI exposes Stellen, Praktika and Lehrstellen as filters backed by one
  unfiltered endpoint. Traineeships and target groups are attributes, not separate feeds.
- Native identity: explicit Prospective numeric `jobs[].id`.
- Canonical detail identity: `links.directlink`; its path retains the stable Prospective
  `viewkey` UUID and the page publishes JobPosting JSON-LD.
- Exhaustion: the API accepts a complete in-memory response and reports `total`. Multi-request
  offsets were observed to reorder and overlap rows, so they are not authorized as scientific
  pagination. The adapter requests one bounded complete feed and requires rows, unique IDs and
  `total` to be equal; exceeding the capacity fails closed for a new access/contract review.
- Observed evidence: first response reported 502 records; this is not configuration.
- Publication: API `start_date` is publication evidence (`SOURCE_FIELD`, exact datetime).
- Update: `last_modification_timestamp` is kept only as `source_updated_at`.
- Location: JSON-LD/source fields only; no municipality is inferred from the federal employer.
- Robots: `jobs.admin.ch` allows `/`; `ohws.prospective.ch` has an empty disallow rule.
- Redirect/origins: API on `ohws.prospective.ch`; detail remains on `jobs.admin.ch`. Job-Room is
  neither requested nor authorized.
- Adapter: configured reuse of the validated Prospective public-v1 and JSON-LD contract.
- Terminal state: `ACCEPTED_IMPLEMENTED`.

## `SRC-OFF-CANTON-AG`

- Official landing: `https://www.ag.ch/de/ueber-uns/jobs-karriere/offene-stellen`.
- Verified platform: Aargau jobs frontend, backed by the official proxy
  `/io/jobs-proxy/{attributes,jobs}` over Umantis data.
- Surfaces: the feed contains ordinary roles and Praktika; category metadata also governs
  apprenticeship presentation. The hub separately links `schulen-aargau.ch/stellen`, a public
  school-employer market rather than a Kanton Aargau direct-employer publication surface.
- Native identity: explicit feed `id`; canonical detail uses `jobs.ag.ch/.../<viewkey>`.
- Pagination: complete in-memory feed with reported `total`.
- Publication/update/location: `startDate`, `lastModificationTimestamp`, and explicit
  `Arbeitsort` attributes are distinguishable.
- Access: `www.ag.ch/robots.txt` explicitly disallows `/io/*`; the only complete official feed
  is therefore not authorized for collection. The separate `/app/sajato-api/` prohibition is
  not used as a substitute explanation.
- Production collection requests: 0. No endpoint or adapter is registered.
- Day-0 target role: `REQUIRED`.
- Terminal state: `ACCEPTED_BLOCKED` (`BLOCKED_PENDING_ACCESS_REVIEW`).

## `SRC-OFF-CANTON-BE`

- Official landing: `https://www.jobs.sites.be.ch/de/start/jobs.html`.
- Verified platform: Sites BE landing with four independent embedded applications.
- Ordinary surface: `https://www.jobs.apps.be.ch/?lang=de`, Prospective Career Center
  `1001760`.
- Apprenticeship surface: `https://www.jobs.apps.be.ch/lehrstelle/?lang=de`, Prospective Career
  Center `1001761`.
- Teaching surface: `https://www.ksml.apps.be.ch/ksml/`.
- Substitute-teaching surface: `https://www.steze.apps.be.ch/`.
- The ordinary feed also exposes official detail links on more than one employer origin,
  including `www.jobs.apps.be.ch` and `jobs.unibe.ch`; origins cannot be authorized dynamically.
- Prospective identities are explicit vacancy UUID/direct links; ordinary and apprenticeship
  forms use offset pagination. No complete common identity contract was proven for KSML/STEZE.
- Access: `www.jobs.apps.be.ch/robots.txt` allows `/`; mandatory KSML and STEZE robots/access
  requests return 403, and STEZE itself returns 403 to the reconnaissance client.
- Production collection requests: 0. No partial ordinary/apprenticeship run is accepted.
- Day-0 target role: `REQUIRED`.
- Terminal state: `ACCEPTED_BLOCKED` (`BLOCKED_PENDING_ACCESS_REVIEW`).

## `SRC-OFF-CANTON-BS`

- Frozen official URL: `https://jobs.arbeitgeber.bs.ch/` (legacy SuccessFactors surface).
- Current institutional landing: the former `www.arbeitgeber.bs.ch/jobs/offene-jobs.html`
  redirects to a `www.bs.ch` page embedding `https://stellenmarkt.bs.ch/kbs/`.
- Verified current platform: Solique-rendered HTML (publication IDs and `saPubId` evidence),
  with SuccessFactors used as an application destination rather than canonical detail.
- Governed surfaces:
  - ordinary: `https://stellenmarkt.bs.ch/kbs/`;
  - apprenticeships: `https://stellenmarkt.bs.ch/kbs/lehrstellen/`.
- Internships and Volontariate are categories of the ordinary surface. No category prefilter is
  applied.
- Native identity: numeric Solique publication ID in `/job/details/<id>` and `saPubId`.
- Canonical detail: the same `stellenmarkt.bs.ch` publication, containing title, organization,
  tasks/profile/benefits and the downstream application link.
- Pagination: cumulative `?page=N` responses; each page repeats earlier rows. The adapter emits
  only new identities, requires exact next-page progression while below the surface total, and
  treats total equality as terminal even when the UI repeats the last next link.
- Observed evidence: ordinary 96 unique IDs over 16 listing requests; apprenticeships 0 over
  one complete request. Zero is a valid complete surface. Counts are not constants.
- Publication/update: no trustworthy publication or update evidence on the canonical detail;
  both remain unknown. A start-of-employment phrase is not publication evidence.
- Location: map coordinates and “Arbeitsort anzeigen” are not converted into a municipality;
  unresolved remains null.
- Access: no clear automation prohibition was published for the current public listing/detail
  paths. Only `www.bs.ch` and `stellenmarkt.bs.ch` are governed collection origins; CDN,
  analytics, maps, Solique tracking and SuccessFactors application origins are not fetched.
- Adapter: new exact-Source HTML adapter using the shared pipeline and multi-surface contract.
- Terminal state: `ACCEPTED_IMPLEMENTED`.

## `SRC-OFF-CANTON-LU`

- Official landing: `https://stellen.lu.ch/`.
- Administration surface: `https://apply.refline.ch/891537/positions_verwaltung.html`.
- Cantonal teacher/pedagogy surface:
  `https://apply.refline.ch/891537/positions_lehrpersonen.html?businessUnit=lehrpersonal`.
- Apprenticeship surface: official redirect through `tinyurl.com` to `https://lehre.lu/map`.
- Municipal-school links are navigation to other employers and are not silently folded into the
  direct canton-employer Source.
- Refline exposes explicit position IDs and canonical publication paths; robots allows these
  paths. Administration and teaching can therefore be translated independently.
- The Nuxt apprenticeship map embeds profession/training profiles, locations, a `free` flag and
  profile update timestamps. It does not prove that each open placement has a unique vacancy ID
  and one canonical vacancy detail. Using the profession slug or profile ID would conflate a
  training profile with one or more positions.
- Publication semantics cannot be invented from profile `updated_at`.
- Production collection requests: 0; Refline is not partially promoted.
- Day-0 target role: `REQUIRED`.
- Terminal state: `ACCEPTED_BLOCKED` (`BLOCKED_PENDING_ACCESS_REVIEW`).

## `SRC-OFF-CANTON-SG`

- Official landing: `https://www.sg.ch/ueber-den-kanton-st-gallen/arbeitgeber-kanton-stgallen/stellenportal.html`.
- Administration surface: official iframe on
  `https://recruitingapp-2800.umantis.com/Jobs/All?...`.
- Verified administrative vendor: Umantis; native IDs are numeric `/Vacancies/<id>/Description/1`.
- Pagination: tokenized `tc1152481=pN` next links, 25 rows per response, exhausted by the
  terminal navigation state. Detail HTML supplies title, organization, tasks and explicit
  workplace text; no reliable publication date was observed.
- Robots on the canton Umantis host does not disallow `/Jobs/All` or `/Vacancies/...`; this is
  independent of the already blocked city St. Gallen AbaShop origin.
- The official employer hub separately advertises “Stellen für Lehrpersonen” and “Ausbildung
  beim Kanton”. Apprenticeships and Praktika appear in Umantis, but completeness relative to the
  separate teaching/training surfaces was not proven. An administration-only run would not be
  `FULL_SOURCE` under the gate rule.
- Production collection requests: 0. No Umantis SourceEndpoint is registered for the canton,
  and city St. Gallen remains unchanged and blocked.
- Day-0 target role: `REQUIRED`.
- Terminal state: `ACCEPTED_BLOCKED` (`BLOCKED_PENDING_ACCESS_REVIEW`).

## Controlled live acceptance

### Federal Administration

- Run: efc8d5e2-c566-4657-ab5b-689bb3aa3b16.
- Adapter: FederalProspectiveAdapter.
- Governed origins: ohws.prospective.ch (API/listing) and jobs.admin.ch (detail).
- Listing surfaces/requests: unified feed, 1 request.
- Reported / unique / details / ACTIVE observations / green assessments:
  502 / 502 / 502 / 502 / 502.
- Cross-surface duplicates: 0 (one unified native-ID feed).
- Green: 1 GREEN_CONFIRMED, 8 REVIEW, 493 NOT_GREEN.
- Publication/update: 502 SOURCE_FIELD publication datetimes; 502 distinct source update
  timestamps. Collection time and update time were never substituted for publication.
- Municipality: 0 exact, 502 unresolved.
- Lifecycle evidence in this accepted run: 16 NEW, 486 STILL_ACTIVE; failed
  reconnaissance runs remain immutable historical evidence and supplied no negative lifecycle
  evidence.
- Result: SUCCEEDED, HEALTHY, snapshot_complete=true.

### Basel-Stadt

- Run: 402e8088-78d1-4db2-88a6-635989601dd7.
- Adapter: BaselStadtSoliqueAdapter.
- Governed origins: www.bs.ch (landing) and stellenmarkt.bs.ch (listing/detail).
- Listing requests: ordinary 16; apprenticeships 1.
- Reported / unique / details / ACTIVE observations / green assessments:
  96 / 96 / 96 / 96 / 96.
- Cross-surface duplicates: 0 in the live run; fixture coverage proves identical native
  identity collapse and conflicting canonical identity failure.
- Green: 0 GREEN_CONFIRMED, 0 REVIEW, 96 NOT_GREEN.
- Publication/update: 96 MISSING, 0 update timestamps.
- Municipality: 0 exact, 96 unresolved.
- Lifecycle: 96 NEW, no negative evidence.
- Result: SUCCEEDED, HEALTHY, snapshot_complete=true.

The four ACCEPTED_BLOCKED Sources each have zero production requests, zero
SourceEndpoint rows and zero collection runs. Job-Room and Job-Room API requests are 0.
Stadt St. Gallen requests are 0 and its blocked state is unchanged.

## Aligned downstream PIT

Shared as_of: 2026-08-11T02:00:00+02:00.

- DedupRun: 01988d96-e10b-4ae1-9fb2-f1ed1243184d,
  fingerprint ad926c6367c751fbf49e0f241fff248db10900e903280c4383441d18a8fbfb37.
- PremiumSegmentRun: a287f860-511b-40a1-b6c9-3e51d12bdc9a,
  fingerprint ccd9a5e0365dfca92c8a87eabd91d88ac4114fe5c09f63471a3ba446d10a9aa8.
- DashboardSnapshot: ac6704ae-bf5f-481a-9d17-18fd205a42ca,
  fingerprint cc2df7cafafb663f1b4dc066eaee062411192d8ef71ecfe0752376bbe3291536.
- Day0ReadinessAssessment: 256ebe14-da78-4062-8e21-716f054de1b3,
  fingerprint 86a88d97086747d3e0d12c4285a2422f498b1dd1bb3838cf44317f7967c88f40.
- Exact replay reused all four exact artifacts and fingerprints.
- Selected postings / effective vacancies: 1,501 / 1,501.
- AUTO_MERGE: 0; cross-source AUTO_MERGE: 0.
- Dedup REVIEW: 98, all noncritical. The seven existing reviews remain; the 91 new
  Federal pairs are individually recorded in gate_011c2_downstream_audit_v0_1.md and its
  seven review parts.
- Premium: 1,501 observations considered; 12 green eligible; 12
  NO_SUFFICIENT_EVIDENCE; 1,489 SKIPPED_NOT_GREEN.
- Public GREEN_CONFIRMED: 12; green REVIEW not public: 38; critical green reviews: 38.
- Mappable / unmappable public green: 0 / 12.
- Required complete / healthy: 11 / 29 and 11 / 29; coverage 37.93%.
- This gate has four explicitly blocked required Sources. The current proposed Day-0 policy
  independently retains REQUIRED_SOURCE_ACCESS_REVIEW for all 29 required Sources until a
  later access-governance gate; that policy field is not relabelled here.
- Readiness: DAY_0_THRESHOLD_POLICY_PENDING.
- Threshold policy: PENDING; freshness policy: PENDING; no market figure authorized.

## Integrity and policy

- No additional Source identity is authorized.
- No Job-Room or Job-Room API request is authorized.
- No blocked Source receives a production network request.
- Threshold policy: `PENDING`.
- Freshness policy: `PENDING`.
- Day-0 market figure: not authorized.
