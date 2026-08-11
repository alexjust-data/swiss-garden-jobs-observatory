# ADR 0013 — GATE-011C-5 hard-blocker resolution wave 2

Status: accepted for implementation, pending draft-PR audit
Date: 2026-08-11
Baseline: `bbd4ea637878fed1388c0f14d03ec5fba097f956`

## Scope

Exactly these required sources are re-evaluated:

- `SRC-OFF-CANTON-AG`
- `SRC-OFF-CANTON-BE`
- `SRC-OFF-CANTON-FR`
- `SRC-OFF-CANTON-GL`
- `SRC-OFF-CANTON-OW`
- `SRC-OFF-CANTON-SH`
- `SRC-OFF-CANTON-UR`
- `SRC-OFF-CANTON-VS`
- `SRC-OFF-CITY-STGALLEN`

AI, JU and NW are deliberately excluded because C-4 already re-evaluated their
semantic/identity blockers.

## Decision

Coverage is admitted only through an authorized, deterministic and auditable
contract for the complete actual vacancy universe. Technical reachability is
not authorization.

- Applicable robots prohibitions are terminal for this gate unless a separate
  official complete origin is proven.
- Authentication credentials, private frontend tokens and personal sessions
  are not acquired or reused.
- Production acquisition remains governed GET/POST. Browser execution is not a
  production acquisition method.
- An alternate ATS/feed is authorized only when the official employer links it
  and identity plus exhaustion are proven.
- Exact source ID and verified platform family are required before adapter
  activation. Vendor similarity alone never authorizes another source.
- A mandatory surface failure makes the complete run fail and supplies no
  negative lifecycle evidence.

## Terminal results

| Source | Result | Basis |
|---|---|---|
| AG | `ACCEPTED_BLOCKED` | complete proxy path is robots-prohibited; no complete independent official origin |
| BE | `ACCEPTED_BLOCKED` | mandatory teaching/substitute surfaces remain inaccessible/incomplete |
| FR | `ACCEPTED_BLOCKED` | active migration and mandatory multi-platform universe remain unreconciled |
| GL | `ACCEPTED_IMPLEMENTED` | official public Umantis unified feed with numeric IDs and total exhaustion |
| OW | `ACCEPTED_BLOCKED` | required Zentraljob tenant publishes `Disallow: /` |
| SH | `ACCEPTED_IMPLEMENTED` | official public Umantis unified feed with allowed listing/details and total exhaustion |
| UR | `ACCEPTED_BLOCKED` | two controlled runs timed out on mandatory official details; no healthy complete acceptance |
| VS | `ACCEPTED_BLOCKED` | administration/teaching/training platforms cannot yet be exhausted as one source |
| Stadt St. Gallen | `ACCEPTED_IMPLEMENTED` | official modern Solique feed unifies ordinary, learner and practicum openings |

## Vacancy and employer boundaries

- GL and SH static career/training information is not promoted; actual current
  apprenticeship/practicum publications occur in the unified Umantis feed.
- UR standing profession/capacity material is non-vacancy information; actual
  openings must occur as stable rows in `/stellen`, but the source remains
  blocked because detail acquisition did not complete reliably.
- Stadt St. Gallen's official employer page explicitly includes roads,
  electricity and parks in the city employment proposition. Its linked Solique
  tenant is therefore the governed canonical employment surface, including
  Stadtwerke rows published there.
- No source identity implies workplace canton or municipality. Empty raw
  geography stays empty.

## Implementation

- A configured public-Umantis translation contract serves exact GL and SH
  sources without globally authorizing Umantis.
- The modern Solique translation contract is parameterized without changing
  Zürich's accepted wire semantics, then activated only for exact Stadt SG.
- SharedCollectionPipeline remains sole owner of RAW/SHA, identity,
  observations, green relevance, lifecycle, source health and FULL_SOURCE.
- No migration is required.

## Day-0 effect

The three newly accepted implementations completed controlled healthy complete
live runs. The aligned result is `20 / 29` complete and healthy, nine
blocked/incomplete, and 68.965517% observed coverage. Blocked sources stay in
the denominator. Threshold and freshness remain `PENDING`; the Day-0 market
figure remains unauthorized regardless of resulting coverage.

Frozen research and the semantics of GATE-008, GATE-009, GATE-010, GATE-011A,
GATE-011B and GATE-011C-1 through C-4 are unchanged.
