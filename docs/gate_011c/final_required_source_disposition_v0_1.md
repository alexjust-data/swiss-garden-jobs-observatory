# GATE-011C-6 final required-source disposition v0.1

Observed on 2026-08-11. The merged baseline is
`17f467a2b376273a784f82a0728d4ef6dca42537`. Live availability and counts are
time-bound evidence, never production constants.

## Final nine-source matrix

| Source | Previous blocker | Current source universe | Vacancy surfaces | Separate employers / non-vacancy | Acquisition, identity and exhaustion result | Final state | Primary blocker | Evidence sufficient? |
|---|---|---|---|---|---|---|---|---|
| `SRC-OFF-CANTON-AI` | Abacus access and apprenticeship identity | canton administration plus canton-employer apprenticeships | current ordinary publications; current apprenticeship opportunities | regional apprenticeship directory is multi-employer; Schnupper/information content is non-vacancy | official HTML names current ordinary and apprenticeship demand, but one apprenticeship page carries multiple profession/start-year states without a publication-level canonical URL or native opportunity ID; the Abacus shell does not supply an independently auditable complete contract | `ACCEPTED_BLOCKED` | `SEMANTIC_IDENTITY_BLOCKED` | YES |
| `SRC-OFF-CANTON-AG` | robots-prohibited complete proxy | administration, courts, police, canton schools and apprenticeships | official React/Umantis-backed vacancy component | generic career information is non-vacancy | `www.ag.ch/robots.txt` still prohibits `/io/*`; `jobs.ag.ch` returned an empty response and no independently official complete ATS/feed with identity and exhaustion was proven; the prohibited path was not requested | `ACCEPTED_BLOCKED` | `POLICY_BLOCKED` | YES |
| `SRC-OFF-CANTON-BE` | mandatory teaching/substitute surfaces incomplete | ordinary, apprenticeships/practica, teachers and substitute teachers | Prospective ordinary/training plus KSML and STEZE | linked independent employers are not silently absorbed | the official hub still lists all four channels; ordinary Prospective remains insufficient alone; KSML/STEZE did not resolve in the production network while indexed KSML evidence still shows live publications, so mandatory acquisition cannot be exhausted | `ACCEPTED_BLOCKED` | `MULTI_SURFACE_BLOCKED` | YES |
| `SRC-OFF-CANTON-FR` | active migration and multi-platform ambiguity | administration, police/SITel, teaching, initial training and stages | SuccessFactors plus still-linked legacy/teaching channels | university, hospital and RFSM are separate employers; generic training information is non-vacancy | the official SuccessFactors landing explicitly states that migration is ongoing, limits the new page to named services and links all other positions elsewhere; FR/DE presentation identity and complete cross-platform exhaustion therefore remain unproven | `ACCEPTED_BLOCKED` | `MULTI_SURFACE_BLOCKED` | YES |
| `SRC-OFF-CANTON-JU` | teaching zero state and `Autres` employer boundary | administration, teaching, magistracy and other official categories | CMS JobList categories | apprenticeship/stage information and replacement registration are non-vacancy; `Autres` may contain separate employers | administration publishes current rows and magistracy has an explicit zero state; teaching still exposes contacts/calendar without either entries or an explicit empty contract, while `Autres` remains an unreconciled employer category | `ACCEPTED_BLOCKED` | `SOURCE_UNIVERSE_BLOCKED` | YES |
| `SRC-OFF-CANTON-NW` | apprenticeship opportunity identity | ordinary Solique-linked jobs plus canton apprenticeships/practica | specific ordinary publications; apprenticeship availability rows | police/career profiles are non-vacancy | the apprenticeship page publishes current start-year availability and application contact, but a shared evergreen page represents several occupations/years and does not expose a stable opportunity-level native ID or distinct canonical URL; title/year is not fabricated into identity | `ACCEPTED_BLOCKED` | `SEMANTIC_IDENTITY_BLOCKED` | YES |
| `SRC-OFF-CANTON-OW` | Zentraljob blanket robots prohibition | ordinary, actual apprenticeships and police openings | mandatory Zentraljob minisite | Schnupper and generic training/profile pages are non-vacancy | `management.zentraljob.ch/robots.txt` still returns `Disallow: /`; no independent official complete origin was proven and the prohibited listing was not requested | `ACCEPTED_BLOCKED` | `POLICY_BLOCKED` | YES |
| `SRC-OFF-CANTON-UR` | mandatory detail timeouts | one server-rendered table containing current canton openings; actual apprenticeships must appear there | `/stellen` table and numeric detail publications | static profession/capacity and Schnupper information are non-vacancy | a bounded C-6 experiment produced one fast HTTP 200 for the listing, then a connection timeout on the same listing; this follows two immutable C-5 FULL_SOURCE failures on mandatory details and cannot support a reproducible healthy snapshot | `ACCEPTED_BLOCKED` | `TECHNICAL_RELIABILITY_BLOCKED` | YES |
| `SRC-OFF-CANTON-VS` | cross-platform exhaustion unresolved | administration, teaching, apprenticeships and stages | Liferay/e-recruitment, official-gazette teaching, training channels | independent institutions must remain separate; FR/DE are presentation variants when identity proves equality | the current official landing still routes primary/orientation-school teaching to the gazette and learners/practica to another channel while the e-recruitment application is not server-visible on the landing; no deterministic common identity/exhaustion contract reconciles all mandatory surfaces | `ACCEPTED_BLOCKED` | `MULTI_SURFACE_BLOCKED` | YES |

## Final blocker classes and recovery conditions

| Source | Primary class | What must change before reconsideration |
|---|---|---|
| AI | `SEMANTIC_IDENTITY_BLOCKED` | an official vacancy-level apprenticeship object/URL with deterministic active state and exhaustion, plus a complete authorized ordinary contract |
| AG | `POLICY_BLOCKED` | an independently official complete allowed origin, or a future explicit access-policy decision |
| BE | `MULTI_SURFACE_BLOCKED` | stable authorized and exhaustible KSML/STEZE replacement contracts, or governed evidence that they are outside the canonical Source |
| FR | `MULTI_SURFACE_BLOCKED` | completed migration or an authoritative cross-platform inventory with stable identity and exhaustion |
| JU | `SOURCE_UNIVERSE_BLOCKED` | explicit teaching empty/list contract and resolved same-employer versus separate-employer classification for `Autres` |
| NW | `SEMANTIC_IDENTITY_BLOCKED` | a stable current apprenticeship publication identity/state distinct from profession/year presentation |
| OW | `POLICY_BLOCKED` | an authorized complete official alternate origin or a source/platform policy change |
| UR | `TECHNICAL_RELIABILITY_BLOCKED` | reproducible complete listing and detail delivery under the existing bounded HTTP policy |
| VS | `MULTI_SURFACE_BLOCKED` | deterministic cross-platform ownership, bilingual identity reconciliation and exhaustion for every mandatory surface |

## Acquisition-policy evidence

- No Aargau `/io/*` request and no Obwalden Zentraljob vacancy request was made.
- No browser collection, authentication/session reuse, private token, alternate user
  agent, mirror or Job-Room substitution was used.
- Public checks used ordinary GETs only. On 2026-08-11 the official landings for
  AI, AG, FR, JU, NW, OW and VS returned readable responses; `jobs.ag.ch`
  returned an empty body. Bern's mandatory KSML/STEZE names did not resolve in
  the production network even though current official/indexed evidence proves
  the channels still exist and carry publications.
- Uri was tested only to distinguish a temporary failure from a reproducible
  contract. The sequence was: PowerShell connection failure; `httpx` listing
  HTTP 200 in 0.81 s; later `httpx` listing connection timeout. A complete
  detail pass was therefore neither attempted nor claimed.

## Final scientific accounting

All 29 required Sources now have a governed disposition. Twenty remain
`ACCEPTED_IMPLEMENTED`; these nine are final `ACCEPTED_BLOCKED` under current
contracts. Final disposition is not the same as implementation. C-6 creates no
adapter, endpoint, collection run or migration, and preserves all immutable
failed/experimental evidence.

Threshold and freshness remain `PENDING`. Day-0 market publication remains
unauthorized.
