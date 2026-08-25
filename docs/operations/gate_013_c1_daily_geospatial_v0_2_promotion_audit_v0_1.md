# GATE-013-C1 daily geospatial v0.2 promotion audit v0.1

## Identity

```text
Baseline:
01a28328161fedc77d7c7f6bec4039d9a75925e0

Branch:
codex/gate-013-c1-daily-geospatial-v0-2

Contract-only commit:
3031a738357e4f3e18c436e755148b19ba4bdd22

Contract blob:
e5df1c528bd919919dcc57297da0d4c4f0f6bb86
```

The contract file has not been modified after its isolated predeclaration
commit.

## Authority promotion

```text
Historical cycle v0.1   no geospatial stage
Historical cycle v0.2   geospatial batch v0.1 / resolver v0.1
New cycle v0.3          geospatial batch v0.2 / resolver v0.2
New Dashboard           resolver v0.2
```

The promoted resolver and batch versions come from the merged GATE-010-C5
implementation. There is no runtime option that silently substitutes a different
daily authority.

## Historical replay

Completed v0.1 and v0.2 fixture cycles replayed by exact cycle ID without
consulting the current governed Source cohort and without collector or
geospatial-runner activity. Current v0.3 completed retry also remains
idempotent.

Replay validates:

- supported stored cycle version;
- cycle/configuration version equality;
- trigger and target-cohort equality;
- exact selected Source identities;
- canonical configuration SHA-256;
- the version-specific geospatial stage/batch/resolver pairing.

An internally re-hashed but semantically invalid v0.2/v0.2 pairing fails closed.
Failed v0.1 and v0.2 cycles cannot resume as v0.3.

The active stage independently rejects a returned legacy batch version or a
result tied to another PremiumRun identity/fingerprint before Dashboard
construction. Dependency injection cannot make a v0.3 cycle persist a v0.1
batch while claiming v0.2 authority.

## Day-0 and production boundary

```text
Day-0 policy changes:             0
Source policy changes:            0
privacy/provider changes:         0
schema migrations:                0
real operational DB writes:       0
operational RAW writes:           0
Source HTTP requests:              0
geocoder/provider HTTP requests:   0
scheduler activation:             NO
```

The current `DAY_0_BLOCKED_BY_DATA_QUALITY` consequence remains valid. This gate
only prevents future daily map snapshots from reverting to geospatial v0.1.

## Validation evidence

```text
Focused GATE-012/GATE-013:            33 passed
Expanded operations/C5/Dashboard:   123 passed
Full pytest:                         661 passed, 2 skipped
Browser / Playwright:                  4 passed
Ruff:                               PASS
mypy:                               PASS — 178 H1 targets including manage.py
Django check:                       PASS
makemigrations --check --dry-run:   PASS — no changes
```

One initial full-suite execution used a non-standard temporary RAW setting and
caused the existing default-RAW scope test to fail. Re-running that exact test
with the repository/CI standard `./data/raw` passed, and the complete suite was
then re-run under the standard environment with the result above.

## Independent-audit boundary

These results establish mechanical readiness only. Merge and production launch
remain blocked pending exact-head GitHub checks and independent semantic audit.

