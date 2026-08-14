# GATE-012 Operational Acceptance v0.1

## Identity

- branch head used by the live cycle: `783f09dcfdd074e4f43f67fb62292969c4834443`
- merged operational baseline: `56db937626a38bcbfe8eee6f4653386a24b14d08`
- operating-contract commit: `f2b77eeb5e8514d6a972c3ae95d85b12aab3b22e`
- cycle: `72630745-5100-4f63-92b9-d8e2e35c2a0b`
- trigger: `RECOVERY`
- started: `2026-08-13T23:07:24.699745Z`
- finished: `2026-08-14T00:12:12.576783Z`
- duration: 3,887.877 seconds
- final cutoff: `2026-08-14T00:07:17.897427Z`

## Collection

- governed Sources selected: 20
- blocked Sources selected: 0
- successful, healthy, complete and counter-consistent: 19
- failed: `SRC-OFF-CANTON-TG`
- failure: `PlatformAdapterError: Thurgau surface total changed during pagination`
- failed-source CollectionRun: none
- runtime minimum: 0.983 seconds
- runtime median: 70.629 seconds
- runtime maximum: 1,069.282 seconds (`SRC-OFF-JOBS-ADMIN`)

The failure is fail-closed evidence. It did not manufacture an empty snapshot, negative lifecycle
evidence, or a successful CollectionRun. A single `SOURCE_DEGRADED` warning event was persisted.

## Continuity

- green applications created: 156
- exact historical green applications reused: 70
- green unmatched: 8
- green conflicts: 0
- dedup applications created: 2
- dedup applications reused: 0

No human decision was created by the operational cycle.

## Aligned PIT

| Artifact | ID | Input fingerprint | Rows per fingerprint |
| --- | --- | --- | ---: |
| DedupRun | `5b1113a9-b3e7-4dcc-a34f-759a2bb1cc5b` | `b8f2ab74b4c321916b253f3397b88d81cc5eaee3e03129219cb11dbe1e7d7252` | 1 |
| PremiumSegmentRun | `641fbb6c-25f0-451e-91c2-e3197be4a9d7` | `0a49c84401bcc5804c34573bcaa352fb4f61323420731a0576a608ee3856c35d` | 1 |
| DashboardSnapshot | `0796b785-4da6-488e-b114-674e4209b6e4` | `22cd7a1670427b485387ba7cbf6f0471a101c588251544cae69919abac1a6bc9` | 1 |
| Day0ReadinessAssessment | `542b36ad-7e33-4b22-8019-930df6c5eae8` | `62474a2b3fbeda641e2fe743a53c756a426ec18833703611792e3706bd8b50e3` | 1 |

## Result and replay

- cycle status: `SUCCEEDED_NOT_AUTHORIZED`
- operational health: `AMBER`
- eligible Sources: 19/29
- active confirmed-green Vacancies: 51
- critical green reviews: 3
- critical dedup reviews: 0
- Day-0: `DAY_0_BLOCKED_BY_DATA_QUALITY`
- headline: null

An exact retry of the same cycle ID completed in 1.5 seconds, returned the same cycle and artifact
identities, and reported `exact_cycle_retry_reused=true`. It performed no Source collection. This is
same-cycle idempotency; it is not a synthetic second daily observation.

`PIT_HISTORY_START` is the completion timestamp of this cycle:
`2026-08-14T00:12:12.576783Z`.

## Validation

- full pytest: 433 passed in 212.57 seconds
- focused GATE-012: 18 passed
- Playwright Chromium: 1 passed
- Ruff: passed
- mypy full project: passed, 158 source files
- Django check: passed
- migration drift: none
- existing PostgreSQL migration: no pending migrations
- existing PostgreSQL reference import twice: identical counts
- clean PostgreSQL migration: passed from an empty database
- clean PostgreSQL reference import twice: identical counts
- exact same-cycle retry: passed, with no Source HTTP

The first published acceptance head, `2e423f41d40d1fc9bb76626c23ec743c2b22a70a`, exposed a
Python 3.12 mypy inference difference: Django `TextChoices` members passed to explicitly typed string
parameters were inferred as label/value tuples. The final correction converts each member with `str(...)`
and uses an explicit three-value trigger choice list. Runtime values and scientific semantics are
unchanged. Full pytest again passed 433 tests after the correction.

The backup/restore smoke used a PostgreSQL 16 custom dump of the post-cycle operational database:

- artifact: `.gate012-artifacts/gate012_operational_20260814_001212.dump`
- SHA-256: `3ecccb748ba20c29d6793872fb426562d864e6f6bcc7deed4555190ec865bfb4`
- archive entries: 544
- isolated restore database: `swiss_garden_jobs_gate012_restore_20260814`

The restored database required no migrations, accepted the reference import twice with identical
counts, passed Django check, and exposed cycle `72630745-5100-4f63-92b9-d8e2e35c2a0b` with the
