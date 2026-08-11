# ADR 0012: GATE-011C-4 blocker resolution wave 1

- Status: Accepted for implementation
- Date: 2026-08-11
- Baseline: `81c4c98cce9789fb2b8d4130b8d1e9ae5d7c0a86`

## Decision

GATE-011C-4 re-evaluates exactly AI, LU, SG canton, JU, NW and TG. Every material official careers surface is classified before implementation as `VACANCY_SOURCE_SURFACE`, `NON_VACANCY_SOURCE_SURFACE`, `SEPARATE_EMPLOYER_SOURCE` or `UNRESOLVED`.

The frozen unit of truth remains the underlying employment opportunity. A real job, apprenticeship, internship or teacher opening may be a vacancy. A profession profile, annual cohort statement, standing candidate pool, orientation experience or generic careers page is not promoted merely because it is visible on an employer portal or green-related.

Phase A establishes these terminal results:

- LU, SG canton and TG: `ACCEPTED_IMPLEMENTED`.
- AI, JU and NW: `ACCEPTED_BLOCKED`.

LU's complete vacancy universe is its administration and cantonal-school/teacher Refline lists. The `lehre.lu` map contains training profiles and availability metadata rather than stable vacancy publications and is a `NON_VACANCY_SOURCE_SURFACE`.

SG canton's official Umantis search is one unified actual-vacancy surface. Its governed employer set contains ordinary, teacher, apprenticeship, practicum and entry-role publications with stable numeric IDs. Informational training pages and orientation offerings are non-vacancy. Stadt St. Gallen remains a separate blocked Source.

TG's Govis listing mixes cantonal vacancies with an explicit `Externe Institutionen` category. The complete direct-employer source is proven by exhausting both the unified listing and category 28, then excluding category-28 UUIDs before detail and Posting promotion. Learner occupation profiles and generic practica information are non-vacancy surfaces.

AI remains blocked because the required Abacus tenant contract is not publicly inspectable and cohort availability rows do not provide proven publication identity. JU remains blocked because mandatory teaching/other category empty and employer-boundary semantics are incomplete. NW remains blocked because training availability is not exposed as stable vacancy-level publications. These sources receive no adapter, endpoint or authoritative run.

## Architecture and completeness

Adapters only translate source evidence. `SharedCollectionPipeline` remains sole authority for governed HTTP, immutable RAW/SHA evidence, identity reconciliation, append-only observations, green classification, lifecycle, health and FULL_SOURCE promotion.

Adapter authorization remains exact-source plus verified platform. LU uses an exact Refline adapter, SG an exact Umantis adapter, and TG an exact Govis/Prospective boundary adapter. Vendor similarity cannot activate another Source.

Every required surface must finish. Repeated native ID plus one canonical detail collapses; a conflicting detail fails closed. A malformed or unavailable mandatory surface yields an incomplete/failed run and no negative lifecycle evidence. A healthy complete zero-posting source is valid.

Only actual vacancy acquisition origins receive production endpoints. Non-vacancy and separate-employer URLs remain documented evidence, not listing seeds. Production acquisition remains governed GET/POST; browser automation is not introduced.

## Unchanged contracts and consequences

Publication, update and first-seen timestamps remain distinct. Profile update timestamps are not vacancy publication dates. Municipality derives only from source-published workplace evidence. Green relevance and dedup remain downstream and unchanged.

Graubünden `stage.html` remains a `NON_VACANCY_SOURCE_SURFACE`: Schnupperlehre is not requested or promoted. AG, BE, FR, GL, OW, SH, UR, VS, Stadt St. Gallen, Job-Room and Job-Room API are outside this gate.

GATE-008, GATE-009, GATE-010, GATE-011A, GATE-011B and GATE-011C-1/2/3 semantics are unchanged. Frozen research is unchanged.

Day-0 remains unauthorized. Coverage is diagnostic only. Threshold and freshness policies remain `PENDING`.
