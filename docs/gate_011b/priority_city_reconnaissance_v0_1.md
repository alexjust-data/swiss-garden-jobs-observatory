# GATE-011B priority city reconnaissance v0.1

Reconnaissance date: 2026-08-10. Only the four identities authorized by Decision 0008 were examined. Frozen registry data was not rewritten.

## Bern

- Source: `SRC-OFF-CITY-BERN`
- Frozen family: `JOBS_BERN_CH`
- Verified vendor/family: Prospective current public API
- Landing: `https://www.bern.ch/themen/arbeiten-fuer-die-stadt-bern/offene-stellen`
- Listing API: `https://jobs.bern.ch/public/v1/medium/1840/jobs`
- Detail origin: `https://jobs.bern.ch/offene-stellen/`
- Discovery: JSON `jobs`, integer `total`, deterministic `offset` and `limit`
- Native identity: explicit API job `id`
- Publication evidence: API `start_date`; update evidence: `last_modification_timestamp`
- Detail evidence: individual city-hosted HTML with JobPosting JSON-LD
- Access: registry requires explicit automation-review acknowledgement; robots allows `/`
- Strategy: `NEW_ADAPTER`, sharing Prospective detail translation
- Terminal target: `READY_FOR_IMPLEMENTATION`

The frozen family is a source-specific label rather than a conflicting vendor assertion, so the verified Prospective implementation is not a platform mismatch.

## Luzern

- Source: `SRC-OFF-CITY-LUZERN`
- Frozen family: `CITY_LUZERN_PORTAL`
- Verified vendor/family: Prospective legacy career center (`ohws.prospective.ch` assets)
- Landing: `https://jobs.stadtluzern.ch/stellen/offene-stellen-stadt-luzern/`
- Listing/detail origin: `https://job.stadtluzern.ch`
- Discovery: HTML form; explicit forward control and POST offset prove exhaustion
- Native identity: numeric `job-<id>` on each listing link
- Publication evidence: JobPosting JSON-LD `datePosted`; update evidence unavailable
- Location evidence: JobPosting JSON-LD address only
- Access: registry requires explicit automation-review acknowledgement
- Strategy: `GENERALIZE` shared Prospective detail translation; legacy HTML discovery remains separate from Bern's API discovery
- Terminal target: `READY_FOR_IMPLEMENTATION`

## St. Gallen

- Source: `SRC-OFF-CITY-STGALLEN`
- Frozen family: `CITY_SG_PORTAL`
- Verified vendor/family: Abacus AbaShop (`meta generator="Abacus AbaShop"`)
- Official landing: `https://www.stadt.sg.ch/home/verwaltung-politik/arbeiten-fuer-stgallen.html`
- Observed recruiting origin: `https://recruiting.stadt.sg.ch`
- Access evidence: `https://recruiting.stadt.sg.ch/robots.txt` returns `Disallow: /`
- Strategy: `BLOCKED`; no adapter and no SourceEndpoint authorization
- Terminal state: `ACCEPTED_BLOCKED`

The frozen family is generic and therefore not contradicted, but access policy prevents automation. The source remains required and blocked in the Day-0 denominator.

## Schaffhausen

- Source: `SRC-OFF-CITY-SCHAFFHAUSEN`
- Frozen family: `UMANTIS_LINKED`
- Verified family: city-owned WordPress listing/detail mirror linked to Umantis applications
- Listing: `https://jobs.stadt-schaffhausen.ch/freie-stellen/`
- Local index: `https://jobs.stadt-schaffhausen.ch/wp-json/wp/v2/jobs`
- Pagination: explicit WordPress next-page links and reported active-inserat total
- Native identity: Umantis vacancy number retained in city slug or explicit Umantis URL
- Detail: city-owned individual job page with JobPosting JSON-LD
- Publication evidence: JSON-LD `datePosted`; update evidence unavailable
- Location evidence: JSON-LD address only
- Redirect/origin rule: no request to `recruitingapp-2808.umantis.com`; an external listing target must have an exact city-owned mirror from the local REST index
- Access: city robots permits public pages/API while admin paths remain disallowed; registry still requires explicit automation-review acknowledgement
- Strategy: `NEW_ADAPTER`
- Terminal target: `READY_FOR_IMPLEMENTATION`

## Fail-closed rules

No city employer name supplies municipality evidence. Missing or ambiguous source location remains null. Reported totals and explicit pagination exhaustion govern FULL_SOURCE status. Conflicting duplicate IDs, missing local mirrors, malformed payloads, unauthorized origins, or unproven pagination prevent a healthy complete snapshot and cannot advance negative lifecycle evidence.
## Controlled live acceptance (2026-08-10)

| Source | Terminal state | Run | Listing/unique/detail/observation/green | Green result | Completeness |
|---|---|---|---|---|---|
| `SRC-OFF-CITY-BERN` | `ACCEPTED_IMPLEMENTED` | `445c20a9-9669-499e-a671-b0c7536ca8b9` | `1 request / 38 / 38 / 38 / 38` | `2 CONFIRMED, 1 REVIEW, 35 NOT_GREEN` | `SUCCEEDED`, `HEALTHY`, `snapshot_complete=true` |
| `SRC-OFF-CITY-LUZERN` | `ACCEPTED_IMPLEMENTED` | `13d6d54c-1a6f-45fc-a20f-50de66d6da4a` | `1 request / 16 / 16 / 16 / 16` | `0 CONFIRMED, 0 REVIEW, 16 NOT_GREEN` | `SUCCEEDED`, `HEALTHY`, `snapshot_complete=true` |
| `SRC-OFF-CITY-STGALLEN` | `ACCEPTED_BLOCKED` | none | zero collection requests | not applicable | recruiting origin publishes `robots.txt: Disallow: /` |
| `SRC-OFF-CITY-SCHAFFHAUSEN` | `ACCEPTED_IMPLEMENTED` | `e31251ee-cce3-4866-b128-26e4d8d177e8` | `4 listing requests / 56 / 56 / 56 / 56` | `1 CONFIRMED, 3 REVIEW, 52 NOT_GREEN` | `SUCCEEDED`, `HEALTHY`, `snapshot_complete=true` |

Schaffhausen's city listing sometimes links directly to Umantis. The collector never fetches
that unauthorized origin. It resolves the stable vacancy ID to the city-owned WordPress record;
city-local detail pages use their JobPosting JSON-LD, while redirect-only entries use the
city-owned WordPress REST detail (`id`, `slug`, `link`, title, publication/update timestamps and
excerpt). Fields absent from REST remain unknown. A narrowly scoped repair handles unescaped
HTML attribute quotes inside the portal's JSON-LD `description`; the repair flag is persisted and
unrelated malformed JSON-LD remains a contract failure.

The numeric Day-0 threshold and maximum freshness remain pending. These runs do not authorize a
Day-0 market figure.
## Temporal replay and Day-0 impact

Second healthy FULL_SOURCE runs proved `STILL_ACTIVE` for all 38 Bern, 16 Luzern and 56
Schaffhausen postings. At aligned `as_of=2026-08-10T18:35:02.713178+02:00`, dedup selected 655
postings and produced 655 effective vacancies, zero AUTO_MERGE and the existing six REVIEW pairs.
The dashboard contains 9 public GREEN_CONFIRMED records and zero safe map features.

GATE-011A readiness assessment `aba512c8-20a5-4a33-a5d1-56b197532624` reports 5/29 required
sources complete and healthy (17.24%). Status remains `DAY_0_THRESHOLD_POLICY_PENDING`; threshold
and freshness policies remain pending, and no market figure is authorized. Exact dashboard and
readiness replays reused their immutable records.